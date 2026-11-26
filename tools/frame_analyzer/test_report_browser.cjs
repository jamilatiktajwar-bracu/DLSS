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

    // Select a metric populated by the synthetic fixture. Locate an actual
    // rendered data-point pixel rather than guessing chart coordinates.
    await page.locator('#metric').selectOption('present_prepare_wall');
    const canvas = page.locator('#chart');
    const bounds = await canvas.boundingBox();
    assert.ok(bounds, 'chart canvas should be visible');
    const point = await canvas.evaluate(node => {
      const ctx = node.getContext('2d');
      const { data, width, height } = ctx.getImageData(0, 0, node.width, node.height);
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const offset = (y * width + x) * 4;
          // The normal (non-selected, non-anomalous) data-point fill is #85d6d6.
          if (data[offset] === 0x85 && data[offset + 1] === 0xd6
              && data[offset + 2] === 0xd6 && data[offset + 3] === 255) {
            return { x: x / (window.devicePixelRatio || 1),
              y: y / (window.devicePixelRatio || 1) };
          }
        }
      }
      return null;
    });
    assert.ok(point, 'chart should contain at least one rendered data point');
    await page.mouse.move(bounds.x + point.x, bounds.y + point.y);
    const hover = page.locator('#hover');
    await page.waitForFunction(() => document.querySelector('#hover').textContent.trim().length > 0);
    assert.match((await hover.textContent()).trim(), /source/);
    await page.mouse.click(bounds.x + point.x, bounds.y + point.y);
    assert.match(await detail.textContent(), /source/,
      'clicking a plotted point should select a frame');
    assert.equal(errors.length, 0, errors.join('\\n'));
    console.log('Browser report smoke and chart/table interaction checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
