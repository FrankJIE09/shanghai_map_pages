#!/usr/bin/env python3
"""Regression checks for every built dining atlas in real responsive viewports.

    python3 build.py
    python3 scripts/atlas_probe.py
    python3 scripts/atlas_probe.py --page hangzhou-michelin --width 390 --keep
    python3 scripts/atlas_probe.py --page shanghai-bars --width 1440 --regressions-only
    python3 scripts/atlas_probe.py --page hong-kong-michelin --home
    python3 scripts/atlas_probe.py --page seoul-michelin --page shanghai-michelin --width 390 --currency-only

Uses an isolated headless Chrome profile and local HTTP server, with source JSON
as the expected data. Online tiles are blocked and geolocation is simulated;
the probe never sends the user's location or opens external navigation links.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import http.server
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading

from merge_venues import merge_sources

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 390, 900, 1440)

PROBE = r"""
<script>
(async function () {
  const f = window.__atlasFixture, results = [], q = s => document.querySelector(s);
  const pause = () => new Promise(resolve => setTimeout(resolve, 80));
  function check(name, pass, detail = '') { results.push({name, pass: Boolean(pass), ...(detail ? {detail} : {})}); }
  const rows = () => [...document.querySelectorAll('#list .row')].map(row => row.dataset.id).sort();
  const pins = () => document.querySelectorAll('.leaflet-marker-icon.pin').length;
  const selectedName = () => q('#detail.selected h2')?.textContent || '';
  const control = (attribute, value) => [...document.querySelectorAll('[' + attribute + ']')].find(el => el.getAttribute(attribute) === value);
  const click = selector => { const el = q(selector); if (!el) throw Error('Missing control ' + selector); el.click(); };
  const choose = id => { const el = control('data-select', id); if (!el) throw Error('Missing restaurant ' + id); el.click(); };
  function input(selector, value) {
    const el = q(selector); el.value = value;
    el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true}));
  }
  function toggle(selector, value) { const el = q(selector); el.checked = value; el.dispatchEvent(new Event('change', {bubbles: true})); }
  const reset = () => click('#reset');
  const visible = selector => { const el = q(selector), rect = el.getBoundingClientRect(); return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  function geometry(state) {
    check('No horizontal overflow: ' + state, document.documentElement.scrollWidth <= innerWidth,
      innerWidth + ' / ' + document.documentElement.scrollWidth);
  }
  function matches(name, expected) {
    const expectedIds = expected.map(r => r.id).sort(), actual = rows();
    check(name + ' directory', JSON.stringify(actual) === JSON.stringify(expectedIds), `${actual.length} / ${expectedIds.length}`);
    check(name + ' markers', pins() === expected.filter(r => r.mapped).length, String(pins()));
  }
  const shown = element => {
    if (!element) return false;
    const rect = element.getBoundingClientRect(), style = getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity) > 0;
  };
  function currencyRegression() {
    if (f.kind !== 'michelin') return;
    reset();
    const expectedOptions = ['', ...[1,2,3,4].map(n => f.currency.repeat(n))];
    check('Price selector uses the city currency',
      JSON.stringify([...q('#price').options].map(option => option.value)) === JSON.stringify(expectedOptions));
    for (const band of expectedOptions.slice(1)) {
      input('#price', band);
      matches('Official price band ' + band, f.records.filter(r => r.priceKey === band));
    }
    if (f.city === 'hong-kong') {
      check('Hong Kong price label identifies Hong Kong dollars', q('#priceFootnote').textContent.includes('港币'));
    }
    reset();
  }
  async function focusedRegressions() {
    reset();
    if (f.kind === 'bars') {
      click('.view-switch [data-view="directory"]');
      if (!q('#advancedFilters').open) click('#advancedFilters summary');
      const aside = q('#directory').getBoundingClientRect(), foot = q('.directory-foot').getBoundingClientRect();
      check('Expanded advanced filters keep the directory footer inside the panel',
        q('#advancedFilters').open && shown(q('.directory-foot')) && foot.bottom <= aside.bottom + 1 && foot.top >= aside.top,
        `footer ${foot.top.toFixed(1)}–${foot.bottom.toFixed(1)} / panel ${aside.top.toFixed(1)}–${aside.bottom.toFixed(1)}`);
      toggle('#onlyLate', true);
      const boundary = f.records.filter(r => r.close === '02:00'), actual = rows();
      const expected = f.records.filter(r => r.late).map(r => r.id).sort();
      check('Inclusive late-night label and results include exactly 02:00 closing',
        q('#lateOption').textContent.includes('2点及以后') && boundary.length > 0 && boundary.every(r => actual.includes(r.id)) &&
        JSON.stringify(actual) === JSON.stringify(expected),
        `${boundary.length} boundary venues; ${actual.length}/${expected.length} late-night results`);
      reset();
      click('#advancedFilters summary');
      click('.view-switch [data-view="map"]');
    }
    if (f.kind === 'eat' || f.kind === 'bichi') {
      const restaurant = f.records.find(r => r.key === 'both_renheguan' && r.michelinLevel === 1);
      if (!restaurant) throw Error('Missing source fixture: one-star 人和馆');
      click('.view-switch [data-view="directory"]');
      input('#search', restaurant.name);
      const rowBadge = control('data-select', restaurant.id)?.querySelector('.michelin-cross');
      if (rowBadge) rowBadge.scrollIntoView({block:'center',behavior:'instant'});
      const rowAward = shown(rowBadge) && rowBadge.textContent.includes('米其林') && rowBadge.textContent.includes('一星');
      choose(restaurant.id); await pause();
      const detailBadge = q('#detail .michelin-cross');
      const marker = [...document.querySelectorAll('.leaflet-marker-icon.pin')].find(el => el.title === restaurant.name);
      const markerBadge = marker?.querySelector('.pin-award');
      const detailAward = shown(detailBadge) && detailBadge.textContent.includes('一星');
      const markerAward = shown(markerBadge) && markerBadge.getAttribute('aria-label')?.includes('一星');
      check('人和馆 retains its one-star award in list, details and map marker',
        rowAward && detailAward && markerAward,
        `list:${rowAward} detail:${detailAward} marker:${Boolean(markerAward)}`);
      reset();
    }
  }
  try {
    const sample = f.sample;
    if (f.currencyOnly) {
      currencyRegression();
      check('No uncaught JavaScript errors', !window.__probeErrors.length, window.__probeErrors.join('; '));
      window.__atlasProbe = {page:f.id,width:innerWidth,results};
      return;
    }
    if (f.regressionsOnly) {
      await focusedRegressions();
      check('No uncaught JavaScript errors', !window.__probeErrors.length, window.__probeErrors.join('; '));
      window.__atlasProbe = {page:f.id,width:innerWidth,results};
      return;
    }
    matches('Initial source records', f.records);
    check('Initial deep link opens source restaurant', selectedName() === sample.name && q('.pin.active'));
    check('City picker lists all configured maps and current map', q('#mapPicker').options.length === f.mapCount && q('#mapPicker').value === f.file);
    check('Page title uses guide edition', q('#pageTitle').textContent.includes(f.edition));
    if (f.kind === 'michelin') {
      check('Source-derived starred and Bib totals', Number(q('#starTotal').textContent) === f.records.filter(r => ['1','2','3'].includes(r.category)).length && Number(q('#bibTotal').textContent) === f.records.filter(r => r.category === 'bib').length);
    }
    geometry('initial');
    currencyRegression();

    for (const [category, count] of Object.entries(f.categories)) {
      reset();
      const button = control('data-cat', category);
      check('Category ' + category + ' source count', button && Number(button.querySelector('b').textContent) === count);
      if (!count) { check('Empty category ' + category + ' is disabled', button.disabled); continue; }
      button.click();
      matches('Category ' + category, f.records.filter(r => r.tags.includes(category)));
      check('Category ' + category + ' exposes selection', button.getAttribute('aria-pressed') === 'true');
    }
    reset();
    if (f.kind === 'eat' || f.kind === 'bichi') {
      control('data-cat', 'bichi').click(); control('data-cat', 'saojie').click();
      matches('Multi-category union', f.records.filter(r => r.tags.includes('bichi') || r.tags.includes('saojie')));
      check('Both selected categories remain pressed', control('data-cat','bichi').getAttribute('aria-pressed') === 'true' && control('data-cat','saojie').getAttribute('aria-pressed') === 'true');
      reset();
    }
    input('#search', sample.name);
    matches('Name search', f.records.filter(r => r.search.includes(sample.name.toLocaleLowerCase())));
    if (f.city === 'seoul') {
      input('#search', 'mInGlEs'); matches('Case-insensitive Latin search', f.records.filter(r => r.id === '511985'));
      input('#search', '밍글스'); matches('Korean name search', f.records.filter(r => r.id === '511985'));
      input('#search', '江南区'); matches('Chinese district search', f.records.filter(r => r.district === 'Gangnam-gu'));
    }
    reset();
    input('#district', sample.district); input('#cuisine', sample.cuisine); input('#price', sample.priceKey);
    const intersection = f.records.filter(r => (!sample.district || r.district === sample.district) && r.cuisine === sample.cuisine && r.priceKey === sample.priceKey);
    matches('District + cuisine + price intersection', intersection);
    control('data-cat', sample.category).click();
    matches('Category combines with other filters', intersection.filter(r => r.tags.includes(sample.category)));
    input('#search', 'no-such-restaurant-987654');
    matches('Empty search', []);
    check('Empty state offers reset', q('[data-reset]'));
    click('[data-reset]');
    matches('Empty-state reset', f.records);
    check('Reset clears search and all selects', ['search','district','cuisine','price','booking','idCheck'].every(id => q('#'+id).value === ''));

    for (const [selector, field] of [['#onlyNew','isNew'],['#onlyGreen','green'],['#onlyMichelin','michelin'],['#onlyLive','live']]) {
      const expected = f.records.filter(r => r[field]);
      if (!expected.length || q(selector).parentElement.hidden) continue;
      toggle(selector, true); matches(selector, expected); reset();
    }
    if (f.kind === 'bars') {
      toggle('#hideClosed', true); matches('Hide closed and suspended venues', f.records.filter(r => r.status === 'active')); reset();
      input('#booking', sample.booking); matches('Booking requirement', f.records.filter(r => r.booking === sample.booking)); reset();
      toggle('#onlyLate', true); matches('Open until 02:00 or later', f.records.filter(r => r.late)); reset();
    }

    control('data-save', sample.id).click();
    check('Favorite persists under this collection key', JSON.parse(localStorage.getItem(f.storageKey)).includes(sample.id) && q('#favoriteCount').textContent === '1');
    check('Favorite has accessible pressed state', control('data-save', sample.id).getAttribute('aria-pressed') === 'true');
    check('Favorites stay isolated from all other maps', f.storageKeys.filter(key => key !== f.storageKey).every(key => localStorage.getItem(key) === '["foreign-sentinel"]'));
    click('#favoriteFilter'); matches('Favorites-only filter', [sample]); choose(sample.id);
    check('Selection writes compatible share hash', location.hash === '#' + f.hashKey + '=' + encodeURIComponent(sample.id) && selectedName() === sample.name);
    if (f.city === 'seoul') {
      const links = [...document.querySelectorAll('#detail .actions a')];
      check('Korean navigation and official detail remain available', ['map.naver.com','map.kakao.com','www.google.com','guide.michelin.com'].every(host => links.some(a => new URL(a.href).hostname === host)));
      check('Korean navigation carries Korean name and address', links.filter(a => /naver|kakao/.test(a.href)).every(a => decodeURIComponent(a.href).includes(sample.localName) && decodeURIComponent(a.href).includes(sample.localAddress)));
      check('External Korean links protect opener', links.every(a => a.target === '_blank' && a.rel.split(' ').includes('noopener')));
    } else {
      const nav = new URL(q('#detail-nav').href), poi = new URL(q('#detail-poi').href);
      check('Chinese navigation uses WGS-84 source coordinates', nav.searchParams.get('coord_type') === 'wgs84' && nav.searchParams.get('location') === sample.lat + ',' + sample.lng);
      check('Chinese POI search uses the current city', poi.searchParams.get('region') === f.cityName && poi.searchParams.get('coord_type') === 'wgs84' && poi.searchParams.get('location') === sample.lat + ',' + sample.lng);
      check('Chinese map links use same-tab navigation', !q('#detail-nav').target && !q('#detail-poi').target);
      if (f.city === 'hong-kong') {
        const google = [...document.querySelectorAll('#detail .actions a')].find(a => new URL(a.href).hostname === 'www.google.com');
        const search = google ? new URL(google.href).searchParams.get('query') || '' : '';
        check('Hong Kong Google navigation includes venue and city',
          google && search.includes(sample.name) && (search.includes('香港') || /Hong Kong/i.test(search)) && google.rel.split(' ').includes('noopener'));
      }
    }
    geometry('selected details');
    click('#detailSave');
    matches('Unsave in favorites view', []);
    check('Unsave clears detail and persisted collection', !selectedName() && q('#favoriteCount').textContent === '0' && localStorage.getItem(f.storageKey) === '[]');
    check('Other collections survive unfavorite', f.storageKeys.filter(key => key !== f.storageKey).every(key => localStorage.getItem(key) === '["foreign-sentinel"]'));
    reset();

    input('#search', 'no-such-restaurant-987654');
    location.hash = '#' + f.hashKey + '=' + encodeURIComponent(sample.key || sample.id); await pause();
    check('Shared link clears incompatible filters', selectedName() === sample.name && rows().length === f.records.length && !q('#search').value);
    location.hash = ''; await pause();
    check('Clearing hash removes stale detail and active marker', !selectedName() && !q('.pin.active'));
    location.hash = '#r=unknown-restaurant-id'; await pause();
    check('Unknown shared link is harmless', !selectedName() && rows().length === f.records.length);
    const marker = [...document.querySelectorAll('.leaflet-marker-icon.pin')].find(el => el.title === sample.name);
    marker.click(); check('Map marker opens its restaurant', selectedName() === sample.name);
    input('#search','no-such-restaurant-987654'); check('Filtering clears hidden selection and hash', !selectedName() && !location.hash); reset();

    click('.view-switch [data-view="directory"]');
    if (innerWidth <= 900) {
      check('Mobile directory view shows only directory', visible('#directory') && !visible('#mapPanel') && q('#explorer').dataset.view === 'directory');
      geometry('mobile directory'); choose(sample.id);
      check('Mobile selection returns to map and details', visible('#mapPanel') && !visible('#directory') && selectedName() === sample.name);
    } else check('Desktop shows map and directory together', visible('#mapPanel') && visible('#directory'));
    reset();
    click('#distance'); await pause();
    check('Distance sorting uses simulated local position', q('#distance').getAttribute('aria-pressed') === 'true' && q('#filterHint').textContent.includes('直线距离'));
    check('Located distances do not produce NaN', !q('#list').textContent.includes('NaN'));
    if (f.unmapped.length) {
      check('Unlocated archive sorts behind mapped restaurants', rows().length === f.records.length && [...q('#list').children].slice(-f.unmapped.length).every(row => f.unmapped.some(r => r.id === row.dataset.id)));
      reset();
      for (const archived of f.unmapped) {
        input('#search', archived.name); matches('Unlocated archive searchable', [archived]); choose(archived.id);
        check('Unlocated archive opens without creating a marker', selectedName() === archived.name && pins() === 0 && !q('#detail-nav'));
        check('Unlocated archive explains uncertainty', q('#detail').textContent.includes('核实') && q('#detail').textContent.includes(archived.directoryNote));
        const link = new URL(q('#detail-poi').href);
        check('Unlocated archive has city-scoped name search only', link.searchParams.get('region') === f.cityName && !link.searchParams.has('location'));
        check('Unknown address cannot be copied', q('#copyAddress').disabled);
        click('#fit'); check('Fit with only an archive is safe', q('#toast').textContent.includes('坐标'));
      }
      reset();
    }
    click('#theme'); check('Map theme switch updates state', q('#theme').getAttribute('aria-pressed') === 'true' && q('#map').classList.contains('dark-map'));
    click('#theme'); click('#landmarks'); check('Landmark switch updates state', q('#landmarks').getAttribute('aria-pressed') === 'false'); click('#landmarks');
    if (f.kind === 'bars') {
      check('Shanghai metro controls retain 13 optional lines', !q('#metroControl').hidden && document.querySelectorAll('#metroOptions input').length === 13);
      const pathsBefore = document.querySelectorAll('.leaflet-overlay-pane path').length;
      const line = q('#metroOptions input'); line.checked = true; line.dispatchEvent(new Event('change',{bubbles:true}));
      check('Metro selection adds map geometry', document.querySelectorAll('.leaflet-overlay-pane path').length > pathsBefore);
    }
    click('#aboutBtn');
    check('Source dialog exposes scope and usable sources', q('#about').open && q('#scopeSummary').textContent.includes(String(f.records.length)) && q('#sourceLinks a'));
    geometry('source dialog'); click('#closeAbout'); check('Source dialog closes', !q('#about').open);
    await focusedRegressions();
    check('No uncaught JavaScript errors', !window.__probeErrors.length, window.__probeErrors.join('; '));
  } catch (error) { check('Probe completed without exception', false, error.stack || String(error)); }
  window.__atlasProbe = {page:f.id,width:innerWidth,results};
})();
</script>
"""

HOME_PROBE = r"""
<script>
(() => {
  const f = window.__homeFixture, results = [], q = selector => document.querySelector(selector);
  function check(name, pass, detail = '') { results.push({name, pass: Boolean(pass), ...(detail ? {detail} : {})}); }
  try {
    const groups = [...document.querySelectorAll('main > .country[data-country]')];
    check('Homepage country groups put China before Korea in the DOM',
      JSON.stringify(groups.map(group => group.dataset.country)) === '["china","korea"]');
    check('Homepage renders the China group before Korea',
      q('#china') && q('#korea') && q('#china').getBoundingClientRect().top < q('#korea').getBoundingClientRect().top);
    const cards = [...document.querySelectorAll('a.map-card')];
    const expectedFiles = f.pages.map(page => page.file).sort();
    check('Homepage links every configured map exactly once',
      JSON.stringify(cards.map(card => card.getAttribute('href')).sort()) === JSON.stringify(expectedFiles),
      `${cards.length}/${expectedFiles.length} cards`);
    for (const page of f.pages) {
      const card = cards.find(item => item.getAttribute('href') === page.file);
      check(page.id + ' appears under its country',
        card?.closest('.country')?.dataset.country === (page.country === 'CN' ? 'china' : 'korea'));
      check(page.id + ' homepage count matches source configuration',
        Number(card?.querySelector('.card-count b')?.textContent) === page.expectedCount);
    }
    const hongKong = q('#hong-kong');
    check('Hong Kong is a Chinese city with its own guide link',
      hongKong?.closest('#china') && hongKong.getAttribute('href') === f.pages.find(page => page.city === 'hong-kong')?.file);
    const nav = [...document.querySelectorAll('.masthead .nav a')].map(link => link.getAttribute('href'));
    check('Country navigation follows China then Korea', nav[0] === '#china' && nav[1] === '#korea');
    check('Homepage has no horizontal overflow', document.documentElement.scrollWidth <= innerWidth,
      innerWidth + ' / ' + document.documentElement.scrollWidth);
    check('No uncaught JavaScript errors', !window.__probeErrors.length, window.__probeErrors.join('; '));
  } catch (error) { check('Homepage probe completed without exception', false, error.stack || String(error)); }
  window.__atlasProbe = {page:'home',width:innerWidth,results};
})();
</script>
"""


def storage_key(page):
    return 'seoul-michelin-favorites' if page['city'] == 'seoul' else 'dining-atlas-' + page['id']


def fixture(page, pages):
    sources = [(Path(rel).stem, json.loads((ROOT / rel).read_text())) for rel in page['data']]
    records = merge_sources(sources) if page['kind'] == 'eat' else sources[0][1]
    projected = []
    for record in records:
        category = record.get('type') if page['kind'] == 'bars' else record.get('primary', record.get('category', ''))
        tags = record.get('tags', [category])
        if page['kind'] == 'bichi':
            tags = (['both'] if record['bichi'] and record['saojie'] else []) + (['bichi'] if record['bichi'] else []) + (['saojie'] if record['saojie'] else [])
            category = tags[0]
        category = category.replace('michelin', '')
        tags = [tag.replace('michelin', '') for tag in tags]
        address = record.get('address', record.get('addr', ''))
        district = record.get('district', '')
        if page['city'] == 'shanghai' and not district:
            match = re.match(r'([^市]{2,5}区)', address)
            district = match.group(1) if match else ''
        price = re.search(r'[¥₩$]{1,4}', record.get('price', ''))
        avg = record.get('avg')
        price_key = (price.group() if price else '') if page['kind'] == 'michelin' else 'unknown' if not avg else 'under100' if avg < 100 else '100to300' if avg < 300 else '300to1000' if avg < 1000 else 'over1000'
        coords = record.get('coords', [record.get('lat'), record.get('lng')])
        mapped = all(type(value) in (int, float) and math.isfinite(value) for value in coords)
        projected.append({
            'id': str(record.get('id', record['key'])), 'key': record['key'], 'name': record['name'],
            'category': category, 'tags': tags, 'district': district,
            'cuisine': record['genre'] if page['kind'] == 'bars' else record.get('cuisine', ''),
            'priceKey': price_key, 'mapped': mapped, 'lat': coords[0], 'lng': coords[1],
            'localName': record.get('koreanName', ''), 'localAddress': record.get('koreanAddress', address),
            'isNew': bool(record.get('isNew') or record.get('distinctionChange') in ('new', 'promoted')),
            'green': record.get('greenStar', False), 'live': record.get('live', False),
            'michelin': bool(record.get('michelin') or any(tag in ('1','2','3','bib') for tag in tags)),
            'michelinLevel': record.get('michelin', 0), 'close': record.get('close'),
            'status': record.get('status', ''), 'booking': record.get('booking', ''),
            'late': bool(record.get('close') and '02:00' <= record['close'] < '12:00'),
            'directoryNote': record.get('directoryNote', ''),
            'search': ' '.join(str(record.get(field, '') or '') for field in ('name','koreanName','englishName','address','addr','koreanAddress','cuisine','metro','type')).lower(),
            'directPoi': bool(record.get('baidu_uid') or record.get('baidu_url')),
        })
    candidates = [record for record in projected if record['mapped'] and record['cuisine'] and record['priceKey'] and not record['directPoi']]
    sample = next((record for record in projected if record['id'] == '511985'), None) or next((record for record in candidates if record['district']), candidates[0])
    categories = {tag: sum(tag in record['tags'] for record in projected) for tag in sorted({tag for record in projected for tag in record['tags']})}
    if page['kind'] == 'michelin':
        categories = {tag: categories.get(tag, 0) for tag in ('3','2','1','bib')}
    return {**{key: page[key] for key in ('id','city','kind','edition','file','cityName','center')},
            'records': projected, 'sample': sample, 'categories': categories,
            'currency': page.get('currency', '₩' if page['city'] == 'seoul' else '$' if page['city'] == 'hong-kong' else '¥'),
            'unmapped': [record for record in projected if not record['mapped']],
            'hashKey': 'v' if page['city'] == 'shanghai' else 'r',
            'storageKey': storage_key(page), 'storageKeys': [storage_key(item) for item in pages], 'mapCount': len(pages)}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome', default=os.environ.get('CHROME'))
    parser.add_argument('--page', action='append', help='Atlas ID to check; repeat to choose multiple maps')
    parser.add_argument('--width', action='append', type=int)
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--regressions-only', action='store_true', help='Only the expanded-filter, late-night-boundary and cross-award regressions')
    parser.add_argument('--currency-only', action='store_true', help='Only source-derived price-band checks on selected Michelin maps')
    parser.add_argument('--home', action='store_true', help='Also check country grouping and links on the homepage (included by default without --page)')
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    chrome = args.chrome or next((shutil.which(name) for name in ('google-chrome','chromium','chromium-browser') if shutil.which(name)), None)
    if not chrome and Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists():
        chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not chrome:
        parser.error('Chrome not found; supply --chrome or CHROME.')
    pages = json.loads((ROOT / 'data/atlas-pages.json').read_text())
    chosen = [page for page in pages if not args.page or page['id'] in args.page]
    if args.page and set(args.page) - {page['id'] for page in pages}:
        parser.error('Unknown atlas ID in --page')
    if args.currency_only and args.regressions_only:
        parser.error('Choose either --currency-only or --regressions-only')
    if args.currency_only:
        chosen = [page for page in chosen if page['kind'] == 'michelin']
        if not chosen:
            parser.error('Currency checks need at least one Michelin map')
    widths = args.width or WIDTHS
    if any(width <= 0 for width in widths) or args.jobs <= 0:
        parser.error('Widths and jobs must be positive')
    work = Path(tempfile.mkdtemp(prefix='atlas-probe-'))
    tasks = []
    for page in chosen:
        source = ROOT / 'dist' / page['file']
        if not source.exists():
            parser.error('Build dist first; missing ' + str(source))
        expected = fixture(page, pages)
        expected['regressionsOnly'] = args.regressions_only
        expected['currencyOnly'] = args.currency_only
        setup = '<script>window.__atlasFixture=' + json.dumps(expected, ensure_ascii=False).replace('</', '<\\/') + r''';
window.__probeErrors=[];addEventListener('error',event=>{if(event.message)window.__probeErrors.push(event.message)});
addEventListener('unhandledrejection',event=>window.__probeErrors.push(String(event.reason)));
for(const key of window.__atlasFixture.storageKeys)localStorage.setItem(key,JSON.stringify(key===window.__atlasFixture.storageKey?[]:['foreign-sentinel']));
Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(success){success({coords:{latitude:window.__atlasFixture.center[0],longitude:window.__atlasFixture.center[1]}});}}});
</script>'''
        document = source.read_text().replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="img-src data: blob:;">' + setup, 1)
        (work / page['file']).write_text(document.replace('</body>', PROBE + '</body>'))
        for width in widths:
            name = page['id'] + '-' + str(width)
            url = page['file'] + '#' + expected['hashKey'] + '=' + expected['sample']['id']
            wrapper = f'''<!doctype html><meta charset="utf-8"><style>body{{margin:0}}iframe{{width:{width}px;height:1000px;border:0}}</style><iframe src="{html.escape(url, quote=True)}" title="Atlas regression"></iframe><pre id="probe-result"></pre><script>const poll=setInterval(()=>{{const result=document.querySelector('iframe').contentWindow.__atlasProbe;if(result){{document.querySelector('#probe-result').textContent=JSON.stringify(result);clearInterval(poll)}}}},100);</script>'''
            (work / (name + '.html')).write_text(wrapper)
            tasks.append((name, width))
    if args.home or not args.page:
        source = ROOT / 'dist/index.html'
        if not source.exists():
            parser.error('Build dist first; missing homepage')
        expected = {'pages': [{key: page[key] for key in ('id','city','country','file','expectedCount')} for page in pages]}
        setup = '<script>window.__homeFixture=' + json.dumps(expected, ensure_ascii=False).replace('</', '<\\/') + r''';
window.__probeErrors=[];addEventListener('error',event=>{if(event.message)window.__probeErrors.push(event.message)});
addEventListener('unhandledrejection',event=>window.__probeErrors.push(String(event.reason)));
</script>'''
        document = source.read_text().replace('<head>', '<head>' + setup, 1)
        (work / 'index.html').write_text(document.replace('</body>', HOME_PROBE + '</body>'))
        for width in widths:
            name = 'home-' + str(width)
            wrapper = f'''<!doctype html><meta charset="utf-8"><style>body{{margin:0}}iframe{{width:{width}px;height:1000px;border:0}}</style><iframe src="index.html" title="Homepage regression"></iframe><pre id="probe-result"></pre><script>const poll=setInterval(()=>{{const result=document.querySelector('iframe').contentWindow.__atlasProbe;if(result){{document.querySelector('#probe-result').textContent=JSON.stringify(result);clearInterval(poll)}}}},100);</script>'''
            (work / (name + '.html')).write_text(wrapper)
            tasks.append((name, width))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), lambda *a, **kw: QuietHandler(*a, directory=str(work), **kw))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def run_task(task):
        name, width = task
        command = [chrome,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
                   '--force-prefers-reduced-motion','--disable-background-networking','--disable-extensions',
                   '--user-data-dir=' + str(work / ('profile-' + name)), '--window-size=1600,1100',
                   '--virtual-time-budget=7000','--dump-dom',f'http://127.0.0.1:{server.server_port}/{name}.html']
        try:
            run = subprocess.run(command, capture_output=True, text=True, timeout=45)
            (work / (name + '.log')).write_text(run.stderr)
            match = re.search(r'<pre id="probe-result">(.*?)</pre>', run.stdout, re.S)
            if not match or not match.group(1):
                (work / (name + '-dom.html')).write_text(run.stdout)
                return name, [{'name':'Browser returned probe report','pass':False,'detail':f'exit {run.returncode}'}]
            result = json.loads(html.unescape(match.group(1)))
            (work / (name + '.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
            return name, result['results']
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            return name, [{'name':'Browser completed probe','pass':False,'detail':str(exc)}]

    failures = assertions = 0
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for future in as_completed([pool.submit(run_task, task) for task in tasks]):
                name, results = future.result()
                assertions += len(results)
                failed = [result for result in results if not result['pass']]
                failures += len(failed)
                for result in failed:
                    print('FAIL {}: {} {}'.format(name,result['name'],result.get('detail','')),flush=True)
                print('{}: {}/{} passed'.format(name,len(results)-len(failed),len(results)),flush=True)
    finally:
        server.shutdown(); server.server_close()
        if args.keep or failures:
            print('Probe artifacts:',work)
        else:
            shutil.rmtree(work)
    print('{}/{} checks passed; {} failures'.format(assertions-failures,assertions,failures))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
