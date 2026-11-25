#!/usr/bin/env python3
"""EU-funded research projects on AI and on engineering topics of the atlas, for the Collaboration page.

Source: the CORDIS open data file of Horizon Europe projects, published by the Publications Office of the
European Union (dataset "CORDIS, EU research projects under HORIZON EUROPE (2021-2027)" on data.europa.eu).
Reuse is allowed under CC BY 4.0 (Commission Decision 2011/833/EU) with the source named. This job reads the
bulk file once a week; it does not query the CORDIS search pages. Only project data is kept (title, acronym,
dates, EU contribution, coordinating organisation and its country, link); no data on persons.

Run: python3 tools/fetch_projects.py   (writes projects.json at the site root)
"""
import csv, io, json, re, sys, time, zipfile, urllib.request, datetime as dt
from pathlib import Path

URLS = ['https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip']
OUT = Path(__file__).resolve().parent.parent / 'projects.json'
TODAY = dt.date.today().isoformat()
KEEP = 160

AI = r'artificial intelligence|machine learning|deep learning|\bAI\b|neural network|foundation model|language model|computer vision|generative'
TOPICS = [('shm', r'structural health monitoring|infrastructure monitoring|bridge monitoring|condition monitoring of (bridges|structures|infrastructure)|digital twins? (of|for) (bridges|buildings|infrastructure|structures|the built)'),
          ('wim', r'weigh[- ]in[- ]motion|traffic load'),
          ('struct', r'\bbridges?\b|structural engineering|civil engineering|earthquake engineering|seismic (design|retrofit|resilience)|civil infrastructure|transport infrastructure'),
          ('materials', r'\bconcrete\b|\bcement\b|construction materials?|building materials?|\basphalt\b'),
          ('geo', r'geotechnic|\btunnels?\b|railway (track|infrastructure)|road (pavement|infrastructure)'),
          ('building', r'building physics|energy performance of buildings|building renovation|fire safety|building envelope'),
          ('sustain', r'built environment|circular construction|sustainable construction|construction (sector|industry|waste)'),
          ('metrology', r'metrolog'),
          ('vision', r'computer vision|image analysis|visual inspection|drone inspection')]

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'European AI Atlas (open data, weekly read of the CORDIS bulk file)'})
    for n in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:
            print('download try', n + 1, 'failed:', e)
            time.sleep(5 + 10 * n)
    return None

def clean(t):
    t = re.sub(r'\s+', ' ', t or '').strip()
    t = re.sub(r'\s*[–—]\s*', ', ', t).replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    t = t.replace('…', '...').replace('!', '.').replace('·', ',').replace('&', 'and')
    return re.sub(r'\s+-\s+', ': ', t)

def rows(z, name):
    member = next((n for n in z.namelist() if n.lower().endswith(name)), None)
    if not member:
        return []
    text = z.read(member).decode('utf-8-sig', errors='replace')
    return list(csv.DictReader(io.StringIO(text), delimiter=';', quotechar='"'))

def main():
    raw = None
    for u in URLS:
        raw = get(u)
        if raw: break
    if not raw:
        print('CORDIS file not read, keeping the previous projects.json'); return 1
    z = zipfile.ZipFile(io.BytesIO(raw))
    print('files in the archive:', z.namelist())
    proj = rows(z, 'project.csv')
    orgs = rows(z, 'organization.csv')
    if not proj:
        print('project.csv missing or empty, keeping the previous file'); return 1
    print('columns:', list(proj[0].keys()))
    coord = {}
    for o in orgs:
        if (o.get('role') or '').lower() == 'coordinator':
            coord[o.get('projectID')] = (clean(o.get('name', '')), (o.get('country') or '').strip())
    items = []
    for p in proj:
        end, start = (p.get('endDate') or '')[:10], (p.get('startDate') or '')[:10]
        if not start or (end and end < TODAY):
            continue                                   # running or upcoming projects only
        title = clean(p.get('title', ''))
        text = title + ' ' + (p.get('objective') or '') + ' ' + (p.get('keywords') or '')
        tp = [k for k, rx in TOPICS if re.search(rx, text, re.I)]
        ai = bool(re.search(AI, text, re.I))
        eng = [k for k in tp if k != 'vision']
        if not eng and not (ai and re.search(AI, title, re.I)):
            continue                                   # an engineering topic of the atlas, or AI named in the title
        pid = (p.get('id') or '').strip()
        if not pid.isdigit():
            continue
        try:
            eu = int(float((p.get('ecMaxContribution') or '0').replace(',', '.')))
        except ValueError:
            eu = 0
        c = coord.get(pid, ('', ''))
        items.append({'id': pid, 'a': clean(p.get('acronym', ''))[:40], 't': title[:200], 's': start, 'e': end, 'eu': eu,
                      'org': c[0][:120], 'cc': c[1], 'tp': tp, 'ai': ai, 'u': 'https://cordis.europa.eu/project/id/' + pid})
    if len(items) < 20:
        print(f'only {len(items)} projects matched, keeping the previous file'); return 1
    # engineering topics first (they are few), then the newest AI projects
    items.sort(key=lambda i: (0 if [k for k in i['tp'] if k != 'vision'] else 1, i['s']), reverse=False)
    eng = [i for i in items if [k for k in i['tp'] if k != 'vision']]
    rest = sorted([i for i in items if i not in eng], key=lambda i: i['s'], reverse=True)
    eng.sort(key=lambda i: i['s'], reverse=True)
    keep = eng[:KEEP * 2 // 3] + rest[:KEEP - min(len(eng), KEEP * 2 // 3)]
    OUT.write_text(json.dumps({'read': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
                               'source': 'European Union, CORDIS, https://cordis.europa.eu, CC BY 4.0',
                               'matched': len(items), 'items': keep}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(len(keep), 'projects written out of', len(items), 'matched,', len(eng), 'on engineering topics')
    return 0

if __name__ == '__main__':
    sys.exit(main())
