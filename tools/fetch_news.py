"""Daily news feed for the atlas: AI data centre news for each EU27 country.

Run by .github/workflows/news.yml. Writes news.json next to index.html; the page reads it
and shows the items in the News tab and in each country factsheet.

Sources are publishers' own RSS feeds, listed in tools/news_sources.json with the country
words, topic words, company names and the patterns that label calls, tenders and events, so they can be
changed without touching this script. Feeds are read side by side and broken XML is repaired. Items from earlier runs
are kept until they are older than max_age_days. Each item keeps
only the headline, date, publisher and a link to the original article. If every fetch fails,
the previous news.json is kept.
"""
import json, os, re, sys, html, time, datetime as dt, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tools" / "news_sources.json").read_text(encoding="utf-8"))
OUT = ROOT / "news.json"
NOW = dt.datetime.now(dt.timezone.utc)
MAX_AGE = dt.timedelta(days=CFG.get("max_age_days", 120))
PER_COUNTRY = CFG.get("per_country", 6)  # the EU bucket keeps twice as many
KEEP = re.compile(CFG["topic_must_match"] + "|" + CFG.get("topic_local", "(?!)"), re.I)
CWORDS = {cc: re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b") for cc, words in CFG["countries"].items()}
ATOM = "{http://www.w3.org/2005/Atom}"
LOCAL = {cc: re.compile(r"\b(" + "|".join(map(re.escape, w)) + ")") for cc, w in CFG.get("countries_local", {}).items()}
INFRA = re.compile(CFG.get("infra_words", "(?!)"), re.I)
GLOBAL = re.compile(CFG.get("global_words", "(?!)"), re.I)
EUW = re.compile(r"\b(" + "|".join(map(re.escape, CFG.get("eu_words", ["EU", "Europe", "European"]))) + r")\b")
# European companies and bodies named without a place ("SAP plans 10,000 job cuts"): the headline counts for their home country
COMP = {name: cc for cc, names in CFG.get("companies", {}).items() for name in names}
COMPRX = re.compile(r"(?<![\w.])(" + "|".join(map(re.escape, sorted(COMP, key=len, reverse=True))) + r")(?![\w])") if COMP else None
# what kind of item it is, shown as a small label on the page: calls, tenders and events must not be lost among news
KINDS = [(k, re.compile(rx, re.I)) for k, rx in CFG.get("kinds", {}).items()]
WORKERS = CFG.get("workers", 12)

def get(url, tries=3):
    """Read one feed; a slow or briefly failing publisher gets two more tries before it is skipped."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (atlas news job)", "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if n == tries - 1:
                raise
            time.sleep(2 + 3 * n)

def when(text):
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            return dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None

def tree(xml_bytes):
    """Parse a feed. Some publishers send a stray "&", control characters or text before the XML;
    those are repaired and parsed again instead of losing the whole feed."""
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError:
        t = xml_bytes.decode("utf-8", "replace").lstrip("\ufeff \r\n\t")
        t = t[t.find("<"):] if "<" in t else t
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
        t = re.sub(r"&(?!#?\w+;)", "&amp;", t)
        t = re.sub(r"^<\?xml[^>]*\?>", "", t)
        return ET.fromstring(t.encode("utf-8"))

def norm(link):
    """One address per article: tracking parameters and the fragment are removed, so the same story is not listed twice."""
    try:
        u = urllib.parse.urlsplit(link.strip())
        q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if not re.match(r"(utm_|fbclid|gclid|mc_|ref$|cmpid|at_)", k, re.I)]
        return urllib.parse.urlunsplit((u.scheme, u.netloc.lower(), u.path, urllib.parse.urlencode(q), ""))
    except ValueError:
        return link.strip()

def kind(title):
    """Call, Tender or Event when the headline says so, otherwise an ordinary news item."""
    for k, rx in KINDS:
        if rx.search(title):
            return k
    return ""

def parse(xml_bytes):
    """Yield (title, summary, link, date) from an RSS 2.0, RSS 1.0 (RDF) or Atom feed."""
    root = tree(xml_bytes)
    for it in root.iter("item"):
        yield (html.unescape((it.findtext("title") or "").strip()),
               re.sub(r"<[^>]+>", " ", html.unescape(it.findtext("description") or "")),
               (it.findtext("link") or "").strip(),
               when(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")))
    RSS1 = "{http://purl.org/rss/1.0/}"
    for it in root.iter(RSS1 + "item"):   # RSS 1.0 (RDF) feeds, used by some national publishers
        yield (html.unescape((it.findtext(RSS1 + "title") or "").strip()),
               re.sub(r"<[^>]+>", " ", html.unescape(it.findtext(RSS1 + "description") or "")),
               (it.findtext(RSS1 + "link") or "").strip(),
               when(it.findtext("{http://purl.org/dc/elements/1.1/}date")))
    for it in root.iter(ATOM + "entry"):
        links = it.findall(ATOM + "link")
        ln = next((l for l in links if l.get("rel", "alternate") == "alternate"), links[0] if links else None)
        yield (html.unescape((it.findtext(ATOM + "title") or "").strip()),
               re.sub(r"<[^>]+>", " ", html.unescape(it.findtext(ATOM + "summary") or it.findtext(ATOM + "content") or "")),
               ln.get("href", "") if ln is not None else "",
               when(it.findtext(ATOM + "published") or it.findtext(ATOM + "updated")))

def clean(t):
    t = re.sub(r"\s+[—–-]\s+", ": ", t).replace("—", ", ").replace("–", "-")
    return t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("!", ".")

def classify(title, summary=""):
    """Return the country code, "EU", or None for one item.

    The headline decides first. If it names no place, the first lines of the summary may: many
    headlines say "data centres" or "AI" and leave the place to the opening sentence.
    The topic must appear in the headline or the summary.
    """
    # the headline must be on topic, or the summary must name the topic at least twice:
    # one passing word in a summary (a robot, a start-up that "uses AI") is not enough
    if not KEEP.search(title) and len(KEEP.findall(summary)) < 2:
        return None
    for text in (title, summary[:400]):
        hits = sorted((m.start(), cc) for cc, rx in CWORDS.items() for m in [rx.search(text)] if m)
        if COMPRX:
            hits += [(m.start(), COMP[m.group(1)]) for m in [COMPRX.search(text)] if m]
            hits.sort()
        if hits:
            return hits[0][1]
        if EUW.search(text):
            return "EU"
    return None

def selftest():
    """Headlines that must be kept or dropped (tools/news_cases.json). Run by the check workflow, so a
    change to the word lists that would lose a known item fails before it is published."""
    cases = json.loads((ROOT / "tools" / "news_cases.json").read_text(encoding="utf-8"))
    bad = 0
    for c in cases:
        got = classify(c["t"], c.get("s", ""))
        if got != c["want"]:
            bad += 1; print(f"SELFTEST FAIL want {c['want']} got {got}: {c['t']}")
        if "k" in c and kind(c["t"]) != c["k"]:
            bad += 1; print(f"SELFTEST FAIL kind want {c['k']!r} got {kind(c['t'])!r}: {c['t']}")
    print(f"selftest: {len(cases) - bad} of {len(cases)} cases pass")
    return 1 if bad else 0

def main():
    rows, seen, ok, near, failed = [], set(), 0, [], []
    feeds = list(CFG["feeds"].items()) + [(k, v["url"], v["cc"]) for k, v in CFG.get("national_feeds", {}).items()]
    # Google News search per country (tools/news_sources.json, google_news): national AI news without adding sources by hand
    GN = CFG.get("google_news", {})
    for cc, (name, hl, gl, term) in GN.get("countries", {}).items():
        feeds.append((f"Google News {cc}", GN["en"].format(name=urllib.parse.quote(name)), cc, "gn-en"))
        if hl and term:
            feeds.append((f"Google News {cc} local", GN["local"].format(term=urllib.parse.quote(term), hl=hl, gl=gl), cc, "gn-local"))

    def read(entry):
        src, urls = entry[0], entry[1]
        for url in ([urls] if isinstance(urls, str) else urls):   # a source may list more than one address
            try:
                return list(parse(get(url)))
            except Exception as e:  # one failing feed must not stop the rest
                print(f"FEED FAIL {src}: {url}: {e}", file=sys.stderr)
        return None

    # feeds are read side by side, so one slow publisher cannot use up the job's time; results are handled in list order
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(read, feeds))
    for entry, feed in zip(feeds, results):
        src, urls, home = entry[:3] if len(entry) >= 3 else (entry[0], entry[1], None)   # a national feed carries its country
        gn = entry[3] if len(entry) == 4 else ""
        if feed is None:
            failed.append(src); continue
        ok += 1
        kept0 = len(rows)
        for title, summary, link, d in feed:
            if not (link.startswith("http") and d):
                continue
            item_src = src
            if gn:   # Google News titles end with " - Outlet": the outlet becomes the source
                m = re.match(r"^(.*\S)\s+-\s+([^-]{2,80})$", title)
                if m:
                    title, item_src = m.group(1), m.group(2).strip()
            link = norm(link)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            if d > NOW + dt.timedelta(days=1) or NOW - d > MAX_AGE:
                continue  # dates in the future or too old are dropped, never shown
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in seen or link in seen:
                continue
            seen.add(key); seen.add(link)
            # EU scope only: the headline must name an EU27 country, or the EU itself.
            # One country per item, the first named in the headline, so an item is never filed twice.
            cc = classify(title, "" if gn else summary)
            if cc is None and gn == "gn-local" and KEEP.search(title) and not GLOBAL.search(title):
                cc = home   # the local edition of that country, found by the local word for AI
            if cc is None and home and not gn and KEEP.search(title):
                # a national publisher: the item counts for its country when the headline names the country in the
                # national language, or is about infrastructure (data centres, supercomputers) and not about a place overseas
                if (home in LOCAL and LOCAL[home].search(title)) or (INFRA.search(title) and not GLOBAL.search(title)):
                    cc = home
            if cc is None:
                if KEEP.search(title):   # on topic but no EU place found: listed in the job log for review
                    near.append(f"{src}: {title[:110]}")
                continue
            row = {"c": cc, "d": d.strftime("%-d %b %Y"), "t": clean(title), "u": link, "src": clean(item_src), "_t": d.timestamp()}
            if kind(title):
                row["k"] = kind(title)
            rows.append(row)
        print(f"FEED OK {src}: {len(feed)} items read, {len(rows) - kept0} kept")
    # publisher feeds hold only their latest items, so earlier days' items are kept until they age out
    if OUT.exists():
        try:
            for r in json.loads(OUT.read_text(encoding="utf-8")).get("items", []):
                d = dt.datetime.strptime(r["d"], "%d %b %Y").replace(tzinfo=dt.timezone.utc)
                inscope = r["c"] in CWORDS or r["c"] == "EU"   # the place may have come from the summary, which is not stored
                if inscope and NOW - d <= MAX_AGE and not any(x["u"] == norm(r["u"]) for x in rows):
                    r = dict(r, _t=d.timestamp())
                    if kind(r["t"]):
                        r["k"] = kind(r["t"])
                    rows.append(r)
        except Exception as e:
            print(f"previous news.json skipped: {e}", file=sys.stderr)
    # items added by hand (tools/news_pinned.json): stories the feeds no longer hold, each checked against its source
    pin = ROOT / "tools" / "news_pinned.json"
    if pin.exists():
        for r in json.loads(pin.read_text(encoding="utf-8")):
            d = dt.datetime.strptime(r["d"], "%d %b %Y").replace(tzinfo=dt.timezone.utc)
            if (r["c"] in CWORDS or r["c"] == "EU") and NOW - d <= MAX_AGE and not any(x["u"] == r["u"] for x in rows):
                rows.append({"c": r["c"], "d": r["d"], "t": clean(r["t"]), "u": r["u"], "src": clean(r["src"]), "_t": d.timestamp()})
    rows.sort(key=lambda r: -r["_t"])
    items, per = [], {}
    for r in rows:
        per[r["c"]] = per.get(r["c"], 0) + 1
        if per[r["c"]] <= PER_COUNTRY * (3 if r["c"] == "EU" else 1):
            items.append(r)
    if ok == 0:
        print("every fetch failed; keeping the previous news.json", file=sys.stderr)
        return 1
    for r in items:
        r.pop("_t")
    OUT.write_text(json.dumps({"updated": NOW.strftime("%-d %b %Y"), "read": NOW.strftime("%Y-%m-%dT%H:%MZ"), "items": items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(items)} items from {ok} feeds")
    # job report: feeds that failed and on-topic headlines that were left out, so gaps are seen and the word lists can be tuned
    kinds = {k: sum(1 for r in items if r.get("k") == k) for k, _ in KINDS}
    report = [f"## News job: {len(items)} items from {ok} of {len(feeds)} feeds", "",
              "**Calls, tenders and events among them:** " + ", ".join(f"{k} {n}" for k, n in kinds.items()), ""]
    if failed: report += ["**Feeds that did not answer:** " + ", ".join(failed), ""]
    report += [f"**On topic but no EU place found ({len(near)}):**", ""] + [f"- {n}" for n in near[:40]]
    print("\n".join(report))
    gs = os.environ.get("GITHUB_STEP_SUMMARY")
    if gs:
        with open(gs, "a", encoding="utf-8") as f: f.write("\n".join(report) + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
