"""Automatic checks for the European AI atlas (index.html).

Run:  python tools/check_atlas.py            (offline checks)
      python tools/check_atlas.py --links    (also checks every source link)

Exit code 1 if anything fails, so GitHub Actions marks the run red.
"""
import json, re, sys, collections, urllib.request, concurrent.futures as cf
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
COPY = ROOT / "europe-ai-atlas.html"
REQUIRED = ["id", "n", "city", "cn", "iso", "cc", "x", "y", "L", "ll", "dom", "sec", "b",
            "news", "people", "meta", "snip", "tp"]
LAYERS = {"factory", "hpc", "research", "industry", "thinker", "project", "campus", "bid", "antenna"}
STATUSES = {"Running", "Operational", "Under construction", "Planned", "Bid", "Selected"}
STOCK = [r"world-class", r"cutting-edge", r"\bdelve", r"\bleverag", r"seamless", r"game.chang", r"\btapestry",
         r"\bvibrant", r"\bpivotal", r"in today's", r"worth knowing", r"landscape around"]
BANNED = {"—": "em dash", "–": "en dash", "“": "curly quote", "”": "curly quote",
          "’": "curly apostrophe", "‘": "curly apostrophe", "…": "ellipsis", "!": "exclamation mark", "·": "middle dot", "≈": "approximately sign"}

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
            if it.get("c") not in D["shp"] and it.get("c") != "EU": fail(f"news.json: unknown country {it.get('c')}")
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
    if not where.endswith((".u", ".url", ".asrc")):
        for w in STOCK:
            if re.search(w, text, re.I): fail(f"{where}: stock phrase '{w}', write it plainly")
def walk(o, where):
    if isinstance(o, str): scan(where, o)
    elif isinstance(o, list): [walk(x, where) for x in o]
    elif isinstance(o, dict): [walk(v, f"{where}.{k}") for k, v in o.items() if k != "d"]
for s in sites: walk(s, s.get("id", "?"))
walk(D.get("cnews", {}), "cnews"); walk(D.get("eunews", []), "eunews")
walk(D["sources"], "sources")
if any(w in html for w in ("ZAG fit", "zagnote", "Useful to ZAG", "For ZAG", "DATA.bands")):
    fail("page still contains the private ZAG rating")
outside = "\n".join(l for l in html.split("\n") if not l.startswith("<script>const DATA=") and len(l) < 20000)
for esc, name in [("\\u2014", "em dash"), ("\\u2013", "en dash"), ("\\u2019", "curly apostrophe"), ("\\u201c", "curly quote"), ("\\u00b7", "middle dot")]:
    if esc in outside: fail(f"page code: contains {name} ({esc})")
scan("page markup", outside)

# 3b. news lists newest first, and every point inside its own country outline
def ndate(d):
    d = re.sub(r"^\d+-(\d+)", r"\1", d.strip())
    for f in ("%d %b %Y", "%b %Y", "%Y"):
        try: return dt.datetime.strptime(d, f)
        except ValueError: pass
    fail(f"unreadable news date {d}"); return dt.datetime(1900, 1, 1)
for s in sites:
    ds = [ndate(n["d"]) for n in s.get("news", [])]
    if ds != sorted(ds, reverse=True): fail(f"{s['id']}: news not newest first")
for k, v in list(D.get("cnews", {}).items()) + [("EU", D.get("eunews", []))]:
    ds = [ndate(n["d"]) for n in v]
    if ds != sorted(ds, reverse=True): fail(f"cnews {k}: not newest first")
def rings(d):
    out, cur = [], []
    for cmd, a, b in re.findall(r"([MLZ])([\d.\-]*)\s*([\d.\-]*)", d):
        if cmd == "M":
            if cur: out.append(cur)
            cur = [(float(a), float(b))]
        elif cmd == "L": cur.append((float(a), float(b)))
    if cur: out.append(cur)
    return out
def inside(x, y, R):
    c = False
    for r in R:
        for i in range(len(r)):
            (x1, y1), (x2, y2) = r[i], r[i - 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c
for s in sites:
    sh = D.get("shp", {}).get(s.get("cc") or "")
    if s.get("x") is not None and sh and not inside(s["x"], s["y"], rings(sh["d"])):
        fail(f"{s['id']}: point lies outside {s['cc']}")

# 3c. every institution and site has an address and coordinates; the terrain view has its library
import os
for s in sites:
    if s.get("L") != "thinker":
        if s.get("lat") is None or s.get("lon") is None: fail(f"{s['id']}: coordinates missing")
        elif not (-30 < s["lon"] < 50 and 25 < s["lat"] < 72): fail(f"{s['id']}: coordinates outside Europe")
        if not s.get("addr"): fail(f"{s['id']}: address missing")
for f in ("vendor/maplibre-gl.js", "vendor/maplibre-gl.css"):
    if not os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f)): fail(f"{f} missing")

# 3d. links are well formed and point at pages, not at geocoder queries
for s in sites:
    for k in ("url", "asrc"):
        u = s.get(k) or ""
        if u and (not u.startswith("http") or u.count("http") > 1 or " " in u): fail(f"{s['id']}.{k}: malformed link {u[:60]}")
        if "nominatim.openstreetmap.org" in u: fail(f"{s['id']}.{k}: geocoder query used as a source")

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

# 9. funding calls: every call has a future-or-recent deadline, an official link and plain typography
_cp = ROOT / "calls.json"
if _cp.exists():
    _cj = json.loads(_cp.read_text(encoding="utf-8"))
    for _c in _cj.get("items", []):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", _c.get("dl", "")): fail(f"calls: {_c.get('id')} has no deadline date")
        if not _c.get("u", "").startswith("https://ec.europa.eu/"): fail(f"calls: {_c.get('id')} link is not on the EU portal")
        scan("calls " + _c.get("id", ""), _c.get("t", ""))

# 10. emoji appear only as country flags; interface symbols are drawn as SVG
for _m in re.finditer(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]", outside):
    fail(f"page markup: emoji {_m.group(0)!r} outside a country flag"); break

# 11. the live news feed covers the EU27 and the EU itself only
_np = ROOT / "news.json"
if _np.exists():
    _EU = set(D.get("eu27", [])) | {"EU"}
    for _n in json.loads(_np.read_text(encoding="utf-8")).get("items", []):
        if _n.get("c") not in _EU: fail(f"news: item outside the EU27 ({_n.get('c')}): {_n.get('t', '')[:60]}")

# 5. optional: every link still answers
if "--links" in sys.argv:
    urls = {s["url"] for s in sites if s.get("url")} | {n["u"] for s in sites for n in s["news"]} | {x[2] for x in D["sources"]}
    urls |= {s["asrc"] for s in sites if s.get("asrc")} | {p["u"] for s in sites for p in s.get("papers", []) if p.get("u")}
    urls |= {n["u"] for v in D.get("cnews", {}).values() for n in v} | {n["u"] for n in D.get("eunews", [])}
    urls = sorted(u for u in urls if u and u.startswith("http"))
    def head(u):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 atlas-link-check"})
        for attempt in (1, 2):   # a slow site gets a second try
            try:
                with urllib.request.urlopen(req, timeout=30) as r: return u, r.status
            except urllib.error.HTTPError as e: return u, e.code
            except Exception as e: err = str(e)[:60]
        return u, err
    with cf.ThreadPoolExecutor(8) as ex:
        for u, st in ex.map(head, urls):
            # 401/403/429 mean the site blocks robots, the page itself is usually fine
            if isinstance(st, int) and st >= 400 and st not in (401, 403, 405, 429):
                fail(f"link {u} answered {st}")
            elif not isinstance(st, int):
                print(f"note: {u} did not answer in time ({st}); sites that hold back robots do this, check it by hand if it repeats")
    print(f"checked {len(urls)} links")

print(f"{len(sites)} entries checked")
if problems:
    print("\n".join("FAIL " + p for p in problems)); sys.exit(1)
print("All checks passed")
