// Capture the real built app; no replacement UI or fixture data.
// Usage: NODE_PATH=/path/to/node_modules node scripts/promo/capture.cjs [baseURL]
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const out = path.join(__dirname, 'sources');
const base = process.argv[2] || 'http://127.0.0.1:8765/dist/';
const pause = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(out, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page = await browser.newPage({viewport:{width:1440,height:940},deviceScaleFactor:1});
  const evidence = [];
  async function open(file) {
    await page.goto(new URL(file, base).href, {waitUntil:'load'});
    await pause(2200);
  }
  async function snap(name, selector) {
    const target = selector ? page.locator(selector) : page;
    await target.screenshot({path:path.join(out,name+'.png')});
    evidence.push({file:name+'.png',page:new URL(page.url()).pathname,viewport:page.viewportSize(),selector:selector||null,hash:new URL(page.url()).hash});
  }
  await open('shanghai_eat_2026.html');
  await page.evaluate(()=>MapBase.getMap().setView([31.225,121.47],13,{animate:false}));
  await pause(2000);
  await snap('eat-overview');
  await snap('shanghai-map','#leaflet-map');
  await page.locator('[data-tag="both"]').click();
  await page.locator('.rest-item[data-key="both_lailai_xiaolong"]').click();
  await pause(2200);
  await page.locator('.leaflet-control-zoom-out').click();
  await pause(2000);
  await page.evaluate(()=>window.scrollTo(0,0));
  await snap('eat-selected');
  await open('shanghai_bars_livehouse_2026.html');
  await page.evaluate(()=>MapBase.getMap().setView([31.225,121.47],13,{animate:false}));
  await pause(1500);
  await snap('night-map','#leaflet-map');
  await page.setViewportSize({width:430,height:1000});
  await page.reload({waitUntil:'load'});
  await pause(1800);
  await snap('bars-mobile');
  await page.locator('#m-bar [data-m-open="list"]').click();
  await page.locator('.venue-item[data-key="yyt_b"]').click();
  await pause(1800);
  await snap('bars-mobile-detail');
  await page.setViewportSize({width:1440,height:940});
  await open('seoul_michelin_2026.html');
  await snap('seoul-overview');
  await snap('seoul-map','#map');
  fs.writeFileSync(path.join(out,'capture-report.json'),JSON.stringify({capturedAt:new Date().toISOString(),method:'Playwright screenshots of local dist/ pages. Shanghai camera centered at 31.225,121.47 / z13 with MapBase.getMap().setView; real controls select the double-list filter, Lai Lai Xiao Long, and Yuyintang B Hall. No DOM/data replacement.',shots:evidence},null,2)+'\n');
  await browser.close();
  console.log(JSON.stringify(evidence,null,2));
})().catch(err=>{console.error(err);process.exit(1)});
