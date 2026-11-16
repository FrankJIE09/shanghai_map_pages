#!/usr/bin/env python3
"""Exercise the built Seoul map in Chrome without third-party test dependencies.

Run after python3 build.py:
    python3 scripts/seoul_probe.py
    python3 scripts/seoul_probe.py --chrome /path/to/chrome --keep

The map runs in real 320/390/900/1440px iframe viewports, avoiding Chrome's
500px minimum outer window on macOS. Online tiles are blocked deliberately;
restaurant search, markers and navigation links must work without them.
"""
import argparse
import html
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parent.parent
WIDTHS = (320, 390, 900, 1440)

PROBE = r"""
<script>
(async function () {
  const results = [], query = s => document.querySelector(s);
  const delay = () => new Promise(resolve => setTimeout(resolve, 70));
  function check(name, condition, detail = '') {
    results.push({name, pass: Boolean(condition), ...(detail ? {detail} : {})});
  }
  const count = () => document.querySelectorAll('#list .row').length;
  const pinCount = () => document.querySelectorAll('.leaflet-marker-icon.pin').length;
  const selectedName = () => query('#detail.selected h2')?.textContent || '';
  const input = (selector, value) => {
    const control = query(selector); control.value = value;
    control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true}));
  };
  const click = selector => {
    const control = query(selector);
    if (!control) throw new Error('Missing control: ' + selector);
    control.click();
  };
  const reset = () => click('#reset');
  const visible = selector => query(selector).getBoundingClientRect().width > 0;
  const geometry = state => check('No horizontal overflow: ' + state,
    document.documentElement.scrollWidth <= innerWidth,
    innerWidth + ' / ' + document.documentElement.scrollWidth);
  try {
    check('Initial directory has 93 restaurants', count() === 93, String(count()));
    check('Initial map has 93 restaurant markers', pinCount() === 93, String(pinCount()));
    check('Initial deep link opens Mingles', selectedName() === 'Mingles' && query('.pin.active'));
    check('Summary shows 42 starred and 51 Bib Gourmand', query('#starTotal').textContent === '42' && query('#bibTotal').textContent === '51');
    geometry('initial');

    for (const [cat, expected] of [['3', 1], ['2', 10], ['1', 31], ['bib', 51], ['all', 93]]) {
      click('[data-cat="' + cat + '"]');
      check('Category ' + cat + ' filters rows and markers to ' + expected,
        count() === expected && pinCount() === expected && query('[data-cat="' + cat + '"]').getAttribute('aria-pressed') === 'true');
    }
    for (const [term, expected] of [['MiNgLeS', 1], ['밍글스', 1], ['江南区', 32], ['参鸡汤', 1]]) {
      input('#search', term);
      check('Search ' + term + ' returns ' + expected, count() === expected && pinCount() === expected);
    }
    reset();
    input('#district', 'Gangnam-gu'); input('#cuisine', 'Korean'); input('#price', '₩₩₩₩');
    check('District + cuisine + price intersection has Mingles and Kwonsooksoo',
      count() === 2 && query('[data-id="511985"]') && query('[data-id="511972"]'));
    click('[data-cat="2"]');
    check('Category combines with other filters', count() === 1 && query('[data-id="511972"]'));
    input('#district', 'Mapo-gu');
    check('Empty intersection clears markers and offers reset', count() === 0 && pinCount() === 0 && query('[data-reset]'));
    click('[data-reset]');
    check('Empty-state reset restores all filters and rows', count() === 93 && pinCount() === 93 &&
      ['search', 'district', 'cuisine', 'price'].every(id => query('#' + id).value === '') && query('[data-cat="all"]').getAttribute('aria-pressed') === 'true');
    input('#search', 'no-such-restaurant-987654');
    check('Unmatched text shows empty state', count() === 0 && query('[data-reset]'));
    reset();

    click('[data-save="511985"]');
    check('Favorite is saved and exposed accessibly', query('#favoriteCount').textContent === '1' &&
      query('[data-save="511985"]').getAttribute('aria-pressed') === 'true' &&
      JSON.parse(localStorage.getItem('seoul-michelin-favorites')).includes('511985'));
    click('#favoriteFilter');
    check('Favorites filter shows only saved restaurant', count() === 1 && pinCount() === 1 && query('[data-id="511985"]'));
    click('[data-select="511985"]');
    check('Row opens details and writes shareable hash', selectedName() === 'Mingles' && location.hash === '#r=511985');
    const links = [...document.querySelectorAll('#detail .actions a')];
    check('Detail offers all four navigation/source links', links.length === 4 &&
      ['map.naver.com', 'map.kakao.com', 'www.google.com', 'guide.michelin.com'].every(host => links.some(a => new URL(a.href).hostname === host)));
    check('Korean navigation carries restaurant name and address', links.slice(0, 2).every(a => decodeURIComponent(a.href).includes('밍글스') && decodeURIComponent(a.href).includes('강남구')));
    check('External detail links protect opener', links.every(a => a.target === '_blank' && a.rel.split(' ').includes('noopener')));
    geometry('selected detail');
    click('#detailSave');
    check('Unsave in favorites view clears row, marker, details and persisted favorite', count() === 0 && pinCount() === 0 &&
      !selectedName() && query('#favoriteCount').textContent === '0' && JSON.parse(localStorage.getItem('seoul-michelin-favorites')).length === 0);
    check('Empty favorites explain how to save', query('#list').textContent.includes('还没有收藏'));
    reset();

    click('[data-cat="bib"]');
    location.hash = '#r=511985';
    await delay();
    check('Deep link clears incompatible filters', selectedName() === 'Mingles' && count() === 93 &&
      query('[data-cat="all"]').getAttribute('aria-pressed') === 'true' && query('.pin.active'));
    location.hash = '';
    await delay();
    check('Removing hash clears selected detail and active marker', !selectedName() && !query('.pin.active'));
    location.hash = '#r=missing-id';
    await delay();
    check('Unknown deep link is harmless', !selectedName() && count() === 93);
    click('.leaflet-marker-icon.pin[title="Mingles"]');
    check('Clicking map marker opens a restaurant', Boolean(selectedName()) && location.hash.startsWith('#r='));
    click('[data-cat="bib"]');
    check('Filtering selected starred restaurant clears stale detail and hash', !selectedName() && !location.hash);
    reset();

    click('.view-switch [data-view="directory"]');
    if (innerWidth <= 900) {
      check('Mobile directory switch shows directory and hides map', visible('#directory') && !visible('#mapPanel') && query('#explorer').dataset.view === 'directory');
      geometry('mobile directory');
      click('[data-select="511985"]');
      check('Mobile row selection returns to visible map and detail', visible('#mapPanel') && !visible('#directory') && selectedName() === 'Mingles' && query('#explorer').dataset.view === 'map');
      click('.view-switch [data-view="directory"]');
      click('.view-switch [data-view="map"]');
      check('Mobile map switch updates pressed state', visible('#mapPanel') && query('.view-switch [data-view="map"]').getAttribute('aria-pressed') === 'true');
    } else {
      check('Desktop keeps both map and directory visible', visible('#mapPanel') && visible('#directory'));
    }
    click('#aboutBtn');
    check('Source dialog opens with verified scope and sources', query('#about').open && query('#scopeSummary').textContent.includes('93') && query('#sourceLinks a'));
    geometry('source dialog');
    click('#closeAbout');
    check('Source dialog closes', !query('#about').open);
    check('No uncaught JavaScript errors', !window.__probeErrors.length, window.__probeErrors.join('; '));
  } catch (error) {
    check('Probe completed without exception', false, error.stack || String(error));
  }
  window.__seoulProbe = {width: innerWidth, results};
})();
</script>
"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome', default=os.environ.get('CHROME'))
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    chrome = args.chrome or next((shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser') if shutil.which(name)), None)
    if not chrome and Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists():
        chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not chrome:
        parser.error('Chrome not found; supply --chrome or CHROME.')
    source = ROOT / 'dist/seoul_michelin_2026.html'
    if not source.exists():
        parser.error('Build dist first: python3 build.py')
    work = Path(tempfile.mkdtemp(prefix='seoul-probe-'))
    errors = '<script>window.__probeErrors=[];addEventListener("error",e=>{if(e.message)window.__probeErrors.push(e.message)});addEventListener("unhandledrejection",e=>window.__probeErrors.push(String(e.reason)));</script>'
    page = source.read_text().replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="img-src data: blob:;">' + errors, 1)
    (work / 'map.html').write_text(page.replace('</body>', PROBE + '</body>'))
    for width in WIDTHS:
        wrapper = f'''<!doctype html><meta charset="utf-8"><style>body{{margin:0}}iframe{{width:{width}px;height:1000px;border:0}}</style><iframe src="map.html#r=511985" title="Seoul map"></iframe><pre id="probe-result"></pre><script>const poll=setInterval(()=>{{const result=document.querySelector('iframe').contentWindow.__seoulProbe;if(result){{document.querySelector('#probe-result').textContent=JSON.stringify(result);clearInterval(poll)}}}},100);</script>'''
        (work / f'probe-{width}.html').write_text(wrapper)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), lambda *a, **kw: QuietHandler(*a, directory=str(work), **kw))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    failed = 0
    assertions = 0
    try:
        for width in WIDTHS:
            command = [chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                       '--force-prefers-reduced-motion', '--disable-background-networking', '--disable-extensions',
                       '--user-data-dir=' + str(work / f'profile-{width}'), '--window-size=1600,1100',
                       '--virtual-time-budget=7000', '--dump-dom',
                       f'http://127.0.0.1:{server.server_port}/probe-{width}.html']
            run = subprocess.run(command, capture_output=True, text=True, timeout=35)
            (work / f'chrome-{width}.log').write_text(run.stderr)
            match = re.search(r'<pre id="probe-result">(.*?)</pre>', run.stdout, re.S)
            if not match or not match.group(1):
                failed += 1
                assertions += 1
                print(f'FAIL {width}px: browser produced no probe report (exit {run.returncode})')
                (work / f'dom-{width}.html').write_text(run.stdout)
                continue
            result = json.loads(html.unescape(match.group(1)))
            (work / f'result-{width}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
            for row in result['results']:
                assertions += 1
                if not row['pass']:
                    failed += 1
                    print(f"FAIL {width}px: {row['name']} {row.get('detail', '')}")
            passed = sum(row['pass'] for row in result['results'])
            print(f'{width}px: {passed}/{len(result["results"])} passed')
    finally:
        server.shutdown()
        server.server_close()
        if args.keep or failed:
            print('Probe artifacts:', work)
        else:
            shutil.rmtree(work)
    print(f'{assertions - failed}/{assertions} checks passed; {failed} failures')
    return int(bool(failed))


if __name__ == '__main__':
    raise SystemExit(main())
