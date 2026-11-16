// Capture real built pages through public UI controls. No replacement data,
// DOM edits, or calls to Leaflet's internal map state.
// NODE_PATH=/path/to/node_modules node scripts/promo/capture.cjs \
//   [http://127.0.0.1:8876/dist/] [--output /path/to/capture-directory]
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const ROOT = path.resolve(__dirname, '../..');
const DESKTOP = {width: 1440, height: 1240};
const MOBILE = {width: 430, height: 960};
const DEFAULT_BASE = 'http://127.0.0.1:8876/dist/';
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function options(argv) {
  let base = DEFAULT_BASE, output = path.join(__dirname, 'sources'), hasBase = false;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') return {help: true};
    if (arg === '--output' || arg === '--base') {
      const value = argv[++i];
      if (!value || value.startsWith('--')) throw new Error(`${arg} requires a value`);
      if (arg === '--output') output = path.resolve(value);
      else { base = value; hasBase = true; }
    } else if (!arg.startsWith('-') && !hasBase) {
      base = arg; hasBase = true;
    } else throw new Error(`Unknown argument: ${arg}`);
  }
  const url = new URL(base);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Base URL must use HTTP or HTTPS');
  if (url.search || url.hash) throw new Error('Base URL must be a directory without a query or fragment');
  if (!url.pathname.endsWith('/')) url.pathname += '/';
  return {base: url.href, output};
}

// Dimensions come from the actual JPEG frame, not the expected viewport/crop.
function jpegDimensions(bytes) {
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) throw new Error('Screenshot is not a JPEG');
  const sof = new Set([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf]);
  let offset = 2;
  while (offset + 3 < bytes.length) {
    if (bytes[offset++] !== 0xff) throw new Error('Malformed JPEG marker');
    while (bytes[offset] === 0xff) offset += 1;
    const marker = bytes[offset++];
    if (marker === 0xda || marker === 0xd9) break;
    if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd8)) continue;
    const length = bytes.readUInt16BE(offset);
    if (length < 2 || offset + length > bytes.length) throw new Error('Malformed JPEG segment');
    if (sof.has(marker)) {
      if (length < 8) throw new Error('Malformed JPEG frame');
      return {height: bytes.readUInt16BE(offset + 3), width: bytes.readUInt16BE(offset + 5)};
    }
    offset += length;
  }
  throw new Error('JPEG has no readable frame dimensions');
}

async function main() {
  const args = options(process.argv.slice(2));
  if (args.help) {
    console.log('Usage: node scripts/promo/capture.cjs [baseURL] [--base URL] [--output DIRECTORY]\nDefault base: ' + DEFAULT_BASE);
    return;
  }
  const {chromium} = require('playwright');
  const commit = execFileSync('git', ['rev-parse', 'HEAD'], {cwd: ROOT, encoding: 'utf8'}).trim();
  const dirty = Boolean(execFileSync('git', ['status', '--porcelain=v1'], {cwd: ROOT, encoding: 'utf8'}).trim());
  const startedAt = new Date().toISOString();
  const actions = [], shots = [], sources = new Map(), pageErrors = [];
  let pageActions = [], currentSource = null;
  fs.mkdirSync(args.output, {recursive: true});
  const launch = {headless: true};
  const macChrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  if (process.env.CHROME_PATH) launch.executablePath = process.env.CHROME_PATH;
  else if (fs.existsSync(macChrome)) launch.executablePath = macChrome;
  const browser = await chromium.launch(launch);
  const page = await browser.newPage({viewport: DESKTOP, deviceScaleFactor: 1, reducedMotion: 'reduce'});
  page.setDefaultTimeout(45000);
  page.setDefaultNavigationTimeout(45000);
  page.on('pageerror', error => pageErrors.push(error.message));

  function record(action, details = {}) {
    const entry = {id: `action-${actions.length + 1}`, at: new Date().toISOString(), action, ...details};
    actions.push(entry); pageActions.push(entry);
  }

  async function settle() {
    // DOM reads only. A failed visible tile aborts capture; no blank-map or
    // synthetic-image fallback is substituted into the recorded interface.
    await page.waitForFunction(() => {
      if (document.readyState !== 'complete' || document.fonts.status !== 'loaded') return false;
      const map = document.querySelector('#map');
      if (!map) return [...document.images].every(image => image.complete && image.naturalWidth > 0);
      const rect = map.getBoundingClientRect();
      if (!rect.width || !rect.height) return true; // Actual mobile directory view.
      if (map.classList.contains('leaflet-zoom-anim')) return false;
      const tiles = [...map.querySelectorAll('img.leaflet-tile')].filter(image => {
        const tile = image.getBoundingClientRect();
        return tile.right > rect.left && tile.left < rect.right && tile.bottom > rect.top && tile.top < rect.bottom;
      });
      return tiles.length > 0 && tiles.every(image => image.complete && image.naturalWidth > 0 && image.classList.contains('leaflet-tile-loaded'));
    }, undefined, {timeout: 45000});
    await page.waitForFunction(() => new Promise(resolve => {
      let previous = '', stableSince = performance.now();
      function frame() {
        const boxes = [...document.querySelectorAll('header,#explorer,#map,#directory,#detail,#search')].map(element => {
          const rect = element.getBoundingClientRect();
          return [element.id || element.tagName, rect.x, rect.y, rect.width, rect.height];
        });
        const positions = [...document.querySelectorAll('.leaflet-map-pane,.leaflet-tile-container,.leaflet-marker-icon')].map(element => getComputedStyle(element).transform);
        const signature = JSON.stringify([scrollX, scrollY, boxes, positions]);
        if (signature !== previous) { previous = signature; stableSince = performance.now(); }
        if (performance.now() - stableSince >= 250) resolve(true);
        else requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }), undefined, {timeout: 15000});
    if (pageErrors.length) throw new Error('Page JavaScript failed: ' + pageErrors.join('; '));
  }

  async function open(file, viewport = DESKTOP) {
    pageActions = [];
    await page.setViewportSize(viewport);
    record('set-viewport', {viewport});
    const url = new URL(file, args.base).href;
    const response = await page.goto(url, {waitUntil: 'load'});
    if (!response || !response.ok()) throw new Error(`Source HTML failed to load: ${url} (${response?.status()})`);
    const bytes = await response.body(), hash = sha256(bytes);
    const sourceFile = 'dist/' + file, localFile = path.join(ROOT, sourceFile);
    if (!fs.existsSync(localFile) || sha256(fs.readFileSync(localFile)) !== hash) {
      throw new Error(`Served HTML does not match this checkout's ${sourceFile}; check the preview server and rebuild`);
    }
    if (sources.has(sourceFile) && sources.get(sourceFile).sha256 !== hash) throw new Error(`Source changed during capture: ${sourceFile}`);
    currentSource = {file: sourceFile, url: response.url(), bytes: bytes.length, sha256: hash};
    sources.set(sourceFile, currentSource);
    record('navigate', {url: page.url(), source: sourceFile, htmlSha256: hash});
    if (file !== 'index.html') {
      await page.locator('#map.leaflet-container').waitFor({state: 'visible'});
      await page.locator('#list .row').first().waitFor({state: 'attached'});
    }
    await settle();
  }

  async function click(selector) {
    await page.locator(selector).click();
    record('click', {selector});
    await settle();
  }

  async function snap(name, selector = null) {
    if (selector) {
      await page.locator(selector).scrollIntoViewIfNeeded();
      record('scroll-into-view-if-needed', {selector});
    }
    await settle();
    const target = selector ? page.locator(selector) : page;
    const screenshotOptions = {type: 'jpeg', quality: 92, animations: 'disabled', caret: 'initial', scale: 'css'};
    if (!selector) screenshotOptions.fullPage = false;
    const bytes = await target.screenshot(screenshotOptions), dimensions = jpegDimensions(bytes);
    const viewport = page.viewportSize();
    if (!selector && (dimensions.width !== viewport.width || dimensions.height !== viewport.height)) throw new Error(`Unexpected viewport dimensions for ${name}`);
    const file = name + '.jpg';
    fs.writeFileSync(path.join(args.output, file), bytes);
    const state = await page.evaluate(() => ({
      hash: location.hash, scroll: {x: scrollX, y: scrollY},
      activeElement: {tag: document.activeElement?.tagName || null, id: document.activeElement?.id || null,
        value: document.activeElement instanceof HTMLInputElement ? document.activeElement.value : null},
      view: document.querySelector('#explorer')?.getAttribute('data-view') || null,
      search: document.querySelector('#search')?.value || '',
      visibleRows: document.querySelectorAll('#list .row').length,
      selectedName: document.querySelector('#detail.selected h2')?.textContent || null,
      loadedTiles: document.querySelectorAll('#map img.leaflet-tile-loaded').length
    }));
    record('screenshot', {file, selector, viewport, animations: 'disabled'});
    shots.push({file, ...dimensions, bytes: bytes.length, sha256: sha256(bytes), capturedAt: new Date().toISOString(),
      url: page.url(), viewport, selector, sourceHtml: {...currentSource}, ...state, actions: [...pageActions]});
    console.log(`${file}: ${dimensions.width}×${dimensions.height}`);
  }

  try {
    await open('index.html');
    await snap('home');
    await open('shanghai_michelin_2026.html');
    await snap('shanghai-overview', '#explorer');
    await snap('shanghai-map', '#map');
    for (const [name, file] of [
      ['beijing', 'beijing_michelin_2027.html'], ['suzhou', 'suzhou_michelin_2026.html'],
      ['nanjing', 'nanjing_michelin_2026.html'], ['hangzhou', 'hangzhou_michelin_2026.html']
    ]) {
      await open(file);
      await snap(name + '-map', '#map');
    }
    await open('hong_kong_michelin_2026.html');
    await snap('hong-kong-overview', '#explorer');
    await snap('hong-kong-map', '#map');
    await open('seoul_michelin_2026.html');
    await snap('seoul-overview', '#explorer');

    await open('shanghai_eat_2026.html', MOBILE);
    await click('.view-switch [data-view="directory"]');
    await page.locator('#search').fill('人和馆');
    record('fill', {selector: '#search', value: '人和馆'});
    await page.locator('[data-select="both_renheguan"]').waitFor({state: 'visible'});
    await settle();
    if (!await page.locator('#search').evaluate(input => input === document.activeElement)) throw new Error('Search lost its real focus before capture');
    await snap('mobile-search');
    await click('[data-select="both_renheguan"]');
    await page.locator('#detail.selected').waitFor({state: 'visible'});
    await page.waitForFunction(() => document.querySelector('#explorer')?.dataset.view === 'map' && location.hash === '#v=both_renheguan');
    await page.locator('#share').scrollIntoViewIfNeeded();
    record('scroll-into-view-if-needed', {selector: '#share', purpose: 'Include navigation, address-copy and share controls'});
    await snap('mobile-detail');

    const report = {
      startedAt, capturedAt: new Date().toISOString(), repository_commit: commit,
      working_tree_dirty: dirty, baseURL: args.base,
      method: 'Real local dist/ pages and public UI controls. Desktop 1440×1240; responsive mobile 430×960. No substituted DOM/data or direct Leaflet map changes. Visible tiles and stable layout required before JPEG screenshots; screenshot animations disabled.',
      environment: {node: process.version, playwright: require('playwright/package.json').version, browser: await browser.version(), deviceScaleFactor: 1, reducedMotion: 'reduce'},
      sources: [...sources.values()], actions, shots
    };
    const manifest = {
      repository_commit: commit, working_tree_dirty: dirty, capturedAt: report.capturedAt,
      capture_basis: 'Actual served HTML is byte-matched to local dist/. HTML and JPEG SHA-256 values identify the captured working tree independently of HEAD.',
      sources: report.sources, images: shots
    };
    fs.writeFileSync(path.join(args.output, 'capture-report.json'), JSON.stringify(report, null, 2) + '\n');
    fs.writeFileSync(path.join(args.output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    console.log(`Captured ${shots.length} JPEGs and ${sources.size} source HTML fingerprints in ${args.output}`);
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
