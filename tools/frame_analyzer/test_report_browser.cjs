// SPDX-License-Identifier: GPL-3.0-only
// Browser-level smoke and interaction checks for the generated offline report.
const { chromium } = require('playwright');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');

(async () => {
  const reportPath = process.env.REPORT_HTML;
  assert.ok(reportPath, 'REPORT_HTML must point to the generated fixture report');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(reportPath).href);
    await page.locator('#chart').waitFor();
    assert.ok(await page.locator('#frames tr').count() > 0, 'frame table should render');
    assert.ok(await page.locator('#metric option').count() > 0, 'chart metrics should populate');

    await page.locator('#frames button.frame-link').first().click();
    const detail = page.locator('#detail-message');
    await detail.waitFor();
    assert.match(await detail.textContent(), /source/);
    assert.ok(await page.locator('#detail-grid table').count() >= 1,
      'selecting a frame should render detail tables');

    // Select a metric populated by the synthetic fixture so the canvas has
    // multiple points to hit regardless of the report's default metric.
    await page.locator('#metric').selectOption('present_api');
    const canvas = page.locator('#chart');
    const bounds = await canvas.boundingBox();
    assert.ok(bounds, 'chart canvas should be visible');
    let hit = null;
    for (let y = 25; y < bounds.height - 25 && !hit; y += 8) {
      for (let x = 70; x < bounds.width - 15; x += 8) {
        await page.mouse.move(bounds.x + x, bounds.y + y);
        const value = (await page.locator('#hover').textContent()).trim();
        if (value) { hit = { x, y, value }; break; }
      }
    }
    assert.ok(hit, 'moving over a plotted point should show hover details');
    await page.mouse.click(bounds.x + hit.x, bounds.y + hit.y);
    assert.match(await detail.textContent(), /source/,
      'clicking a plotted point should select a frame');
    assert.equal(errors.length, 0, errors.join('\n'));
    console.log('Browser report smoke and chart/table interaction checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
