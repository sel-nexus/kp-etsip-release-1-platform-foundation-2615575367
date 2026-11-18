/* Capture representative rendered structure for human and source review. */
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const captures = [];
  for (const [name, viewport] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport });
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' });
    captures.push({ name, accessibility: await page.accessibility.snapshot(), styles: await page.evaluate(() => ({ font: getComputedStyle(document.body).fontFamily, background: getComputedStyle(document.body).backgroundColor, color: getComputedStyle(document.body).color })), html: await page.content() });
    await page.screenshot({ path: `preflight-${name}.png`, fullPage: true });
    await page.close();
  }
  fs.writeFileSync('preflight-output.txt', JSON.stringify(captures, null, 2), 'utf8');
  await browser.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
