// Render the product area of the revision-4 mock (guide band excluded) at 1920 x 1080 for W1–W5,
// so that it can be compared with the Figma frames of the same screens (figma_compare.py).
// Usage: node figma_compare_render.cjs <design-mock-15-work-centered-wide.html> <output dir>
const path = require('path');
const { chromium } = require('playwright');

const [file, output] = process.argv.slice(2);
if (!file || !output) { console.error('usage: node figma_compare_render.cjs <mock html> <output dir>'); process.exit(2); }

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto('file://' + path.resolve(file), { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  // The guide band sits above the product; grow the window by its height so the product area is 1920 x 1080.
  const band = await page.evaluate(() => Math.round(document.querySelector('.wc-sidebar').getBoundingClientRect().top));
  await page.setViewportSize({ width: 1920, height: 1080 + band });
  await page.waitForTimeout(400);
  for (const no of ['W1', 'W2', 'W3', 'W4', 'W5']) {
    await page.click(`[data-guide-step="${no}"]`);
    await page.waitForTimeout(450);
    const target = path.join(output, `mock-${no}.png`);
    await page.screenshot({ path: target, clip: { x: 0, y: band, width: 1920, height: 1080 } });
    console.log(target);
  }
  await browser.close();
})().catch((error) => { console.error(error); process.exit(1); });
