"""Automatic checks for the European AI atlas (index.html).

Run:  python tools/check_atlas.py            (offline checks)
      python tools/check_atlas.py --links    (also checks every source link)

Exit code 1 if anything fails, so GitHub Actions marks the run red.
"""
import json, re, sys, collections, urllib.request, concurrent.futures as cf
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
COPY = ROOT / "europe-ai-atlas.html"
REQUIRED = ["id", "n", "city", "cn", "iso", "cc", "x", "y", "L", "ll", "dom", "sec", "b",
            "news", "people", "meta", "snip", "tp"]
LAYERS = {"factory", "hpc", "research", "industry", "thinker", "project", "campus", "bid", "antenna"}
STATUSES = {"Operational", "Under construction", "Planned", "Bid", "Selected"}
STOCK = [r"world-class", r"cutting-edge", r"\bdelve", r"\bleverag", r"seamless", r"game.chang", r"\btapestry",
         r"\bvibrant", r"\bpivotal", r"in today's", r"worth knowing", r"landscape around"]
BANNED = {"—": "em dash", "–": "en dash", "“": "curly quote", "”": "curly quote",
          "’": "curly apostrophe", "‘": "curly apostrophe", "…": "ellipsis", "!": "exclamation mark"}

problems = []
def fail(msg): problems.append(msg)

html = PAGE.read_text(encoding="utf-8")
line = next(l for l in html.split("\n") if l.startswith("<script>const DATA="))
D, _ = json.JSONDecoder().raw_decode(line[len("<script>const DATA="):])
sites = D["sites"]
TOPICS = {t[0] for t in D.get("topics", {}).get("ai", []) + D.get("topics", {}).get("eng", [])}

# 1. the two published copies stay identical
if COPY.exists() and COPY.read_text(encoding="utf-8") != html:
    fail("europe-ai-atlas.html differs from index.html; copy index.html over it")

# 2. every entry is complete and placed on the map
ids = collections.Counter(s.get("id") for s in sites)
for i, c in ids.items():
    if c > 1: fail(f"duplicate id {i}")
for s in sites:
    sid = s.get("id", "?")
    for k in REQUIRED:
        if k not in s: fail(f"{sid}: missing field {k}")
    if s.get("L") not in LAYERS: fail(f"{sid}: unknown layer {s.get('L')}")
    if s.get("L") != "thinker" and s.get("cc") not in D["shp"]:
        if s.get("cc") not in ("UK", ""): fail(f"{sid}: country code {s.get('cc')} has no shape")
    if s.get("x") is not None and not (0 <= s["x"] <= 1000 and 0 <= s["y"] <= 851):
        fail(f"{sid}: marker outside the map ({s['x']}, {s['y']})")
    if not s.get("tp"): fail(f"{sid}: no topic")
    for k in s.get("tp", []):
        if k not in TOPICS: fail(f"{sid}: unknown topic {k}")
    if "sc" in s or "zr" in s: fail(f"{sid}: private rating fields must stay out of the public page")
    if s.get("st") and s["st"] not in STATUSES: fail(f"{sid}: unknown status {s['st']}")
    if s.get("L") in ("campus", "bid", "antenna", "factory") and not s.get("st"): fail(f"{sid}: compute site without a status")
    for nw in s.get("news", []):
        if not re.match(r"https?://", nw.get("u", "")): fail(f"{sid}: news item without a link: {nw.get('t','')[:50]}")
        if not re.search(r"\d{4}", nw.get("d", "")): fail(f"{sid}: news item without a year: {nw.get('t','')[:50]}")

# 2b. country news: every EU27 country has items, each with a year and a link
for cc in D.get("eu27", []):
    if cc not in D["shp"]: fail(f"eu27 code {cc} has no map shape")
    if not D.get("cnews", {}).get(cc): fail(f"{cc}: no country news")
for cc, items in D.get("cnews", {}).items():
    for nw in items:
        if not re.match(r"https?://", nw.get("u", "")) or not re.search(r"\d{4}", nw.get("d", "")):
            fail(f"news {cc}: item without link or year: {nw.get('t','')[:50]}")

# 2c. the daily feed file, if present
NEWS = ROOT / "news.json"
if NEWS.exists():
    import datetime as dt
    try:
        nj = json.loads(NEWS.read_text(encoding="utf-8"))
        today = dt.date.today()
        for it in nj.get("items", []):
            if it.get("c") not in D["shp"]: fail(f"news.json: unknown country {it.get('c')}")
            if not str(it.get("u", "")).startswith("http"): fail("news.json: item without link")
            try:
                d = dt.datetime.strptime(it["d"], "%d %b %Y").date()
                if d > today + dt.timedelta(days=1): fail(f"news.json: future date {it['d']}")
            except Exception:
                fail(f"news.json: unreadable date {it.get('d')}")
    except Exception as e:
        fail(f"news.json does not parse: {e}")

# 3. typography: plain dashes and straight quotes only, in data and in visible text
def scan(where, text):
    for ch, name in BANNED.items():
        if ch == "!":
            continue
        if ch in text: fail(f"{where}: contains {name}")
    if not where.endswith(".u") and not where.endswith(".url"):
        for w in STOCK:
            if re.search(w, text, re.I): fail(f"{where}: stock phrase '{w}', write it plainly")
def walk(o, where):
    if isinstance(o, str): scan(where, o)
    elif isinstance(o, list): [walk(x, where) for x in o]
    elif isinstance(o, dict): [walk(v, f"{where}.{k}") for k, v in o.items() if k != "d"]
for s in sites: walk(s, s.get("id", "?"))
walk(D.get("cnews", {}), "cnews"); walk(D.get("eunews", []), "eunews")
walk(D["sources"], "sources")
if "ZAG fit" in html or "zagnote" in html or "Useful to ZAG" in html:
    fail("page still contains the private ZAG rating")
outside = "\n".join(l for l in html.split("\n") if not l.startswith("<script>const DATA=") and len(l) < 20000)
for esc, name in [("\\u2014", "em dash"), ("\\u2013", "en dash"), ("\\u2019", "curly apostrophe"), ("\\u201c", "curly quote")]:
    if esc in outside: fail(f"page code: contains {name} ({esc})")
scan("page markup", outside)

# 4. counts shown in the page match the data
dc = collections.Counter(x for s in sites for x in s["dom"])
m = re.search(r'data-d="all" aria-pressed="true">All <u>(\d+)</u>', html)
if not m or int(m.group(1)) != len(sites): fail(f"'All' tab shows {m and m.group(1)}, data has {len(sites)}")
for k, v in dc.items():
    m = re.search(rf'data-d="{k}" aria-pressed="false">[^<]*<u>(\d+)</u>', html)
    if m and int(m.group(1)) != v: fail(f"tab {k} shows {m.group(1)}, data has {v}")
if D.get("dcounts") and dict(D["dcounts"]) != dict(dc): fail("DATA.dcounts is out of date")
cnt = collections.Counter(s["cc"] for s in sites if s["L"] != "thinker")
for k, v in D["shp"].items():
    if v["n"] != cnt.get(k, 0): fail(f"country {k} shading counts {v['n']}, data has {cnt.get(k, 0)}")

# 5. optional: every link still answers
if "--links" in sys.argv:
    urls = sorted({s["url"] for s in sites if s.get("url")} | {n["u"] for s in sites for n in s["news"]} | {x[2] for x in D["sources"]})
    def head(u):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 atlas-link-check"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r: return u, r.status
        except urllib.error.HTTPError as e: return u, e.code
        except Exception as e: return u, str(e)[:60]
    with cf.ThreadPoolExecutor(8) as ex:
        for u, st in ex.map(head, urls):
            # 401/403/429 mean the site blocks robots, the page itself is usually fine
            if not (isinstance(st, int) and (st < 400 or st in (401, 403, 405, 429))):
                fail(f"link {u} answered {st}")
    print(f"checked {len(urls)} links")

print(f"{len(sites)} entries checked")
if problems:
    print("\n".join("FAIL " + p for p in problems)); sys.exit(1)
print("All checks passed")
