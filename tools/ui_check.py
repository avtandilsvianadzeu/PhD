#!/usr/bin/env python3
"""Browser check for the atlas: opens the page in headless Chromium and fails on any script error,
failed request, empty page or broken navigation. Runs in CI on every push (.github/workflows/ui.yml).

Run locally:  python3 tools/ui_check.py            (serves the folder on a free port)
"""
import http.server, socketserver, threading, functools, sys, os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TABS = ['browse', 'rank', 'latest', 'saved', 'minds', 'news', 'src', 'plans', 'calls', 'collab']
problems = []

def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    h = functools.partial(Quiet, directory=str(ROOT))
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, s.server_address[1]

def page_for(b, port, w, h, mobile=False, base='map', hash_=''):
    pg = b.new_page(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile)
    pg.add_init_script(f"localStorage.setItem('atlasBase','{base}')")
    tag = f'{w}x{h}{hash_}'
    pg.on('pageerror', lambda e: problems.append(f'{tag}: script error: {e}'))
    pg.on('response', lambda r: r.status >= 400 and 'localhost' in r.url and not r.url.endswith('favicon.ico') and problems.append(f'{tag}: HTTP {r.status} {r.url}'))
    pg.goto(f'http://localhost:{port}/index.html{hash_}', wait_until='load')
    pg.wait_for_timeout(1800)
    return pg

def main():
    srv, port = serve()
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h, mob in [(1440, 900, False), (1024, 768, False), (390, 844, True)]:
            pg = page_for(b, port, w, h, mob)
            n = pg.evaluate("DATA.sites.length")
            if n < 100: problems.append(f'{w}: only {n} entries loaded')
            if not pg.evaluate("document.querySelector('.pane') && document.querySelector('.pane').textContent.trim().length > 50"):
                problems.append(f'{w}: overview panel is empty')
            for t in TABS:
                pg.evaluate(f"setTab('{t}')"); pg.wait_for_timeout(250)
                if pg.evaluate("(document.querySelector('.pane')||{textContent:''}).textContent.trim().length") < 20:
                    problems.append(f'{w}: page {t} renders empty')
            sid = pg.evaluate("DATA.sites.find(s=>s.L==='factory').id")
            pg.evaluate(f"select('{sid}')"); pg.wait_for_timeout(300)
            if pg.evaluate("(document.querySelector('.pane .ttl')||{}).textContent||''") == '':
                problems.append(f'{w}: entry page has no title')
            pg.evaluate("openCountry('DE')"); pg.wait_for_timeout(300)
            for cc in ('GE', 'AM', 'AZ'):   # countries at the eastern edge open and show their entries
                pg.evaluate(f"openCountry('{cc}')"); pg.wait_for_timeout(300)
                if pg.evaluate("(document.querySelector('.pane')||{textContent:''}).textContent.trim().length") < 40: problems.append(f'{w}: country page {cc} is empty')
            pg.close()
        # links that open a view directly, and the Back button
        for hsh, want in [('#calls', "tab==='calls'"), ('#collab', "tab==='collab'"), ('#minds', "tab==='minds'"), ('#c=SI', "selCn==='SI'"), ('#e=aif-slaif', "sel==='aif-slaif'")]:
            pg = page_for(b, port, 1440, 900, hash_=hsh)
            if not pg.evaluate(want): problems.append(f'link {hsh} does not open its view')
            pg.close()
        pg = page_for(b, port, 1440, 900)
        pg.click('[data-pt=calls]'); pg.wait_for_timeout(300); pg.go_back(); pg.wait_for_timeout(500)
        if pg.evaluate("tab") == 'calls': problems.append('Back button does not leave the Calls page')
        pg.close()
        # country bubbles keep a gap, and "Open data" stays in the title bar on desktop widths
        for w, h, mob in [(1440, 900, False), (1280, 800, False), (1024, 768, False), (390, 844, True)]:
            pg = page_for(b, port, w, h, mob)
            n = pg.evaluate("""(()=>{const a=[...document.querySelectorAll('#clusters .cl:not(.off)')].map(g=>{const c=g.querySelector('circle').getBoundingClientRect();return [c.x+c.width/2,c.y+c.height/2,c.width/2];});let n=0;for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++)if(Math.hypot(a[i][0]-a[j][0],a[i][1]-a[j][1])<a[i][2]+a[j][2])n++;return n;})()""")
            if n: problems.append(f'{w}: {n} pairs of country bubbles overlap')
            if not mob and not pg.evaluate("[...document.querySelectorAll('.pright .pbtn')].every(x=>x.getBoundingClientRect().width>0)"):
                problems.append(f'{w}: a title bar button is hidden')
            pg.close()
        # the satellite view opens first; the page must stay free of script errors whether or not the tiles arrive
        pg = page_for(b, port, 1440, 900, base='sat')
        pg.wait_for_timeout(2500)
        sw = pg.evaluate("[...document.querySelectorAll('#basesw button')].map(x=>x.dataset.b).join(',')")
        if sw != 'sat,map': problems.append(f'base map switcher reads {sw}')
        if pg.evaluate("base") not in ('sat', 'map'): problems.append('satellite view did not open')
        # search: accents, several words and short forms find entries; nonsense finds none
        for term, lo, hi in [('munchen', 1, 60), ('hpc finland', 1, 20), ('zurich monitoring', 1, 20), ('xyzzy', 0, 0)]:
            n = pg.evaluate("(t=>{const q=document.getElementById('q');q.value=t;q.dispatchEvent(new Event('input',{bubbles:true}));return DATA.sites.filter(s=>s.hit!==false).length})", term)
            if not lo <= n <= hi: problems.append(f'search "{term}" finds {n} entries')
        pg.evaluate("(()=>{const q=document.getElementById('q');q.value='';q.dispatchEvent(new Event('input',{bubbles:true}))})()")
        pg.evaluate("setTab('collab')"); pg.wait_for_timeout(300)
        if pg.evaluate("document.querySelectorAll('.cb details').length") < 5: problems.append('Collaboration page lists fewer than 5 topics')
        if pg.evaluate("/ZAG|Zavod za gradbeni/.test(document.querySelector('.pane').textContent)"): problems.append('Collaboration page names the owner institute')
        pg.close()
        b.close()
    srv.shutdown()
    for x in problems: print('FAIL', x)
    print('UI check passed' if not problems else f'{len(problems)} problems')
    return 1 if problems else 0

if __name__ == '__main__':
    sys.exit(main())
