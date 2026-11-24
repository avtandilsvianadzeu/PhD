#!/usr/bin/env python3
"""Open and upcoming EU funding calls and tenders on AI, data and computing, for the atlas Calls tab.

Source: the EU Funding and Tenders portal search service (the public API behind
ec.europa.eu/info/funding-tenders/opportunities). The portal content is reusable under
Commission Decision 2011/833/EU, with the source acknowledged; only call metadata is kept
(title, programme, dates, link), no personal data.

Run: python3 tools/fetch_calls.py   (writes calls.json at the site root)
"""
import json, re, sys, uuid, urllib.request, datetime as dt
from pathlib import Path

API = 'https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***&pageSize=100&pageNumber={}'
OUT = Path(__file__).resolve().parent.parent / 'calls.json'
TODAY = dt.date.today().isoformat()

PROG = [(r'JU-CHIPS|^CHIPS', 'Chips Joint Undertaking'), (r'^HORIZON-EUROHPC|^DIGITAL-EUROHPC|EUROHPC', 'EuroHPC Joint Undertaking'), (r'^HORIZON-', 'Horizon Europe'),
        (r'^DIGITAL-', 'Digital Europe'), (r'^CEF-', 'Connecting Europe Facility'), (r'^EIC|HORIZON-EIC', 'European Innovation Council'),
        (r'^ERASMUS-', 'Erasmus+'), (r'^SMP-', 'Single Market Programme'), (r'^EDF-', 'European Defence Fund'),
        (r'^CHIPS|^HORIZON-JU-CHIPS', 'Chips Joint Undertaking'), (r'^EU4H-', 'EU4Health'), (r'^CERV-', 'Citizens, Equality, Rights and Values'),
        (r'^LIFE-', 'LIFE'), (r'^I3-', 'Interregional Innovation Investments')]
TOPICS = [('AI', r'\bAI\b|artificial intelligence|machine learning|generative|foundation model|large language|LLM|neural|GenAI|trustworthy AI|AI-based|AI-driven'),
          ('Computing', r'\bHPC\b|EuroHPC|supercomput|high[- ]performance computing|quantum comput|exascale|AI factor|gigafactor|cloud|edge computing|data cent'),
          ('Data', r'\bdata\b|data space|digital twin|big data|analytics'),
          ('Robotics', r'robot|autonomous'),
          ('Chips', r'semiconductor|\bchips?\b|microelectronic|processor')]
STATUS = {'31094501': 'Forthcoming', '31094502': 'Open'}

def form():
    b = uuid.uuid4().hex
    parts = [('query', json.dumps({'bool': {'must': [{'terms': {'type': ['1', '2', '8']}}, {'terms': {'status': list(STATUS)}}]}})),
             ('languages', '["en"]'), ('sort', json.dumps({'field': 'sortStatus', 'order': 'ASC'}))]
    body = ''.join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="blob"\r\nContent-Type: application/json\r\n\r\n{v}\r\n' for k, v in parts) + f'--{b}--\r\n'
    return body.encode(), f'multipart/form-data; boundary={b}'

def first(m, k):
    v = m.get(k) or ['']
    return str(v[0]) if v else ''

def main():
    items, seen = [], set()
    for page in range(1, 40):
        body, ct = form()
        req = urllib.request.Request(API.format(page), data=body, method='POST', headers={'Content-Type': ct, 'User-Agent': 'European AI Atlas (open data)'})
        try:
            j = json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as e:
            print('page', page, 'failed:', e); break
        res = j.get('results') or []
        if not res: break
        for x in res:
            m = x.get('metadata') or {}
            ident = first(m, 'identifier')
            if not ident or ident in seen: continue
            title = re.sub(r'\s+', ' ', first(m, 'title') or x.get('summary') or '').strip()
            title = re.sub(r'\s*[\u2013\u2014]\s*', ', ', title).replace('\u2019', "'").replace('\u2018', "'").replace('\u201c', '"').replace('\u201d', '"').replace('\u2026', '...').replace('!', '.').replace('\u00b7', ',')
            text = title + ' ' + ident
            kw = ' '.join(m.get('keywords') or []) + ' ' + ' '.join(m.get('tags') or [])
            tags = [n for n, rx in TOPICS if re.search(rx, text, re.I)]
            if not tags and re.search(r'artificial intelligence|machine learning|high performance computing', kw, re.I): tags = ['AI']
            if not tags or (tags == ['Data'] and not re.search(r'data space|digital twin|data cent', text, re.I)): continue
            dls = sorted(d[:10] for d in (m.get('deadlineDate') or []) if d)
            dl = next((d for d in dls if d >= TODAY), '')
            if not dl: continue
            if len(dls) > 1 and dls[0] < TODAY: continue      # second stage by invitation only
            prog = next((n for rx, n in PROG if re.search(rx, ident)), first(m, 'frameworkProgramme') and 'EU programme' or 'EU programme')
            typ = first(m, 'type')
            kind = 'Project call' if typ == '8' else 'EU call'   # type 8: open calls run by EU-funded projects (cascade funding)
            ccm = first(m, 'callccm2Id') or first(m, 'ccm2Id')
            if typ == '8':
                url = first(m, 'url') or f'https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/tender-details/{ccm}'
            else:
                url = f'https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ident.lower()}'
            opens = (first(m, 'startDate') or '')[:10]
            seen.add(ident)
            items.append({'id': ident, 't': title[:220], 'prog': prog, 'kind': kind, 'st': STATUS.get(first(m, 'status'), 'Open'),
                          'opens': opens, 'dl': dl, 'tags': tags, 'u': url})
        if len(res) < 100: break
    if not items:
        print('no calls read, keeping the previous file'); return 1
    items.sort(key=lambda i: (i['dl'], i['t']))
    OUT.write_text(json.dumps({'read': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
                               'source': 'EU Funding and Tenders portal', 'items': items}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(len(items), 'calls written')
    return 0

if __name__ == '__main__':
    sys.exit(main())
