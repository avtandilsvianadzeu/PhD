"""Daily news feed for the atlas: AI data centre news for each EU27 country.

Run by .github/workflows/news.yml. Writes news.json next to index.html; the page reads it
and shows the items in the News tab and in each country factsheet.

Sources are publishers' own RSS feeds, listed in tools/news_sources.json with the country
words and topic words, so they can be changed without touching this script. Items from earlier runs
are kept until they are older than max_age_days. Each item keeps
only the headline, date, publisher and a link to the original article. If every fetch fails,
the previous news.json is kept.
"""
import json, re, sys, html, datetime as dt, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tools" / "news_sources.json").read_text(encoding="utf-8"))
OUT = ROOT / "news.json"
NOW = dt.datetime.now(dt.timezone.utc)
MAX_AGE = dt.timedelta(days=CFG.get("max_age_days", 120))
PER_COUNTRY = CFG.get("per_country", 6)  # the EU bucket keeps twice as many
KEEP = re.compile(CFG["topic_must_match"], re.I)
CWORDS = {cc: re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b") for cc, words in CFG["countries"].items()}
ATOM = "{http://www.w3.org/2005/Atom}"
EUW = re.compile(r"\b(" + "|".join(map(re.escape, CFG.get("eu_words", ["EU", "Europe", "European"]))) + r")\b")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (atlas news job)", "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

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

def parse(xml_bytes):
    """Yield (title, summary, link, date) from an RSS 2.0 or Atom feed."""
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        yield (html.unescape((it.findtext("title") or "").strip()),
               re.sub(r"<[^>]+>", " ", html.unescape(it.findtext("description") or "")),
               (it.findtext("link") or "").strip(),
               when(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")))
    for it in root.iter(ATOM + "entry"):
        ln = it.find(ATOM + "link")
        yield (html.unescape((it.findtext(ATOM + "title") or "").strip()),
               re.sub(r"<[^>]+>", " ", html.unescape(it.findtext(ATOM + "summary") or "")),
               ln.get("href", "") if ln is not None else "",
               when(it.findtext(ATOM + "updated") or it.findtext(ATOM + "published")))

def clean(t):
    t = re.sub(r"\s+[—–-]\s+", ": ", t).replace("—", ", ").replace("–", "-")
    return t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("!", ".")

def main():
    rows, seen, ok = [], set(), 0
    for src, url in CFG["feeds"].items():
        try:
            feed = list(parse(get(url))); ok += 1
        except Exception as e:  # one failing feed must not stop the rest
            print(f"{src}: {e}", file=sys.stderr); continue
        for title, summary, link, d in feed:
            text = title + " " + summary
            if not (link.startswith("http") and d and KEEP.search(text)):
                continue
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            if d > NOW + dt.timedelta(days=1) or NOW - d > MAX_AGE:
                continue  # dates in the future or too old are dropped, never shown
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            # EU scope only: the headline must name an EU27 country, or the EU itself.
            # One country per item, the first named in the headline, so an item is never filed twice.
            hits = sorted((m.start(), cc) for cc, rx in CWORDS.items() for m in [rx.search(title)] if m)
            if hits:
                cc = hits[0][1]
            elif EUW.search(title):
                cc = "EU"
            else:
                continue
            rows.append({"c": cc, "d": d.strftime("%-d %b %Y"), "t": clean(title), "u": link, "src": clean(src), "_t": d.timestamp()})
    # publisher feeds hold only their latest items, so earlier days' items are kept until they age out
    if OUT.exists():
        try:
            for r in json.loads(OUT.read_text(encoding="utf-8")).get("items", []):
                d = dt.datetime.strptime(r["d"], "%d %b %Y").replace(tzinfo=dt.timezone.utc)
                inscope = (r["c"] in CWORDS and CWORDS[r["c"]].search(r["t"])) or (r["c"] == "EU" and EUW.search(r["t"]))
                if inscope and NOW - d <= MAX_AGE and not any(x["u"] == r["u"] for x in rows):
                    rows.append(dict(r, _t=d.timestamp()))
        except Exception as e:
            print(f"previous news.json skipped: {e}", file=sys.stderr)
    rows.sort(key=lambda r: -r["_t"])
    items, per = [], {}
    for r in rows:
        per[r["c"]] = per.get(r["c"], 0) + 1
        if per[r["c"]] <= PER_COUNTRY * (2 if r["c"] == "EU" else 1):
            items.append(r)
    if ok == 0:
        print("every fetch failed; keeping the previous news.json", file=sys.stderr)
        return 1
    for r in items:
        r.pop("_t")
    OUT.write_text(json.dumps({"updated": NOW.strftime("%-d %b %Y"), "items": items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(items)} items from {ok} feeds")
    return 0

if __name__ == "__main__":
    sys.exit(main())
