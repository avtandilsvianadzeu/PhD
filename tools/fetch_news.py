"""Daily news feed for the atlas: AI data centre news for each EU27 country.

Run by .github/workflows/news.yml. Writes news.json next to index.html; the page reads it
and shows the items in the News tab and in each country factsheet.

Sources and search terms live in tools/news_sources.json, so they can be changed
without touching this script. If every fetch fails, the previous news.json is kept.
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
PER_COUNTRY = CFG.get("per_country", 6)
KEEP = re.compile(CFG["title_must_match"], re.I)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (atlas news job)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def parse(xml_bytes):
    """Yield (title, link, date, source) from an RSS 2.0 feed."""
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        when = it.findtext("pubDate")
        try:
            d = parsedate_to_datetime(when) if when else None
        except (TypeError, ValueError):
            d = None
        if not src and " - " in title:
            title, src = title.rsplit(" - ", 1)
        elif src and title.endswith(" - " + src):
            title = title[: -len(" - " + src)]
        yield title.strip(), link, d, src

def clean(t):
    t = re.sub(r"\s+[—–]\s+", ", ", t).replace("—", ", ").replace("–", "-")
    return t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("!", ".")

def main():
    items, seen, ok = [], set(), 0
    for cc, name in CFG["countries"].items():
        q = CFG["query"].replace("{country}", name)
        url = CFG["feed"].replace("{q}", urllib.parse.quote(q))
        try:
            feed = list(parse(get(url))); ok += 1
        except Exception as e:  # one failing country must not stop the rest
            print(f"{cc}: {e}", file=sys.stderr); continue
        rows = []
        for title, link, d, src in feed:
            if not (link.startswith("http") and d and KEEP.search(title)):
                continue
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            if d > NOW + dt.timedelta(days=1) or NOW - d > MAX_AGE:
                continue  # dates in the future or too old are dropped, never shown
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            rows.append({"c": cc, "d": d.strftime("%-d %b %Y"), "t": clean(title), "u": link, "src": clean(src), "_t": d.timestamp()})
        rows.sort(key=lambda r: -r["_t"])
        items += rows[:PER_COUNTRY]
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
