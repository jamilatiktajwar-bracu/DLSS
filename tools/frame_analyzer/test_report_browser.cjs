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

    // Select a metric populated by the synthetic fixture. Read a real plotted
    // point in CSS-pixel coordinates so the browser input targets the same
    // coordinate space used by the report's pointer handlers.
    await page.locator('#metric').selectOption('present_prepare_wall');
    const canvas = page.locator('#chart');
    const bounds = await canvas.boundingBox();
    assert.ok(bounds, 'chart canvas should be visible');
    const point = await canvas.evaluate(() => {
      const candidate = plotted.find(item => Number.isFinite(item.x)
        && Number.isFinite(item.y) && item.row && item.row.source && item.row !== selected);
      return candidate ? { x: candidate.x, y: candidate.y, source: candidate.row.source } : null;
    });
    assert.ok(point, 'chart should contain at least one plotted data point');
    // Dispatch through the canvas DOM event path using its own bounding box;
    // this avoids host mouse-coordinate rounding at fractional CSS scales.
    await canvas.evaluate((node, target) => {
      const rect = node.getBoundingClientRect();
      node.dispatchEvent(new MouseEvent('mousemove', {
        bubbles: true, clientX: rect.left + target.x, clientY: rect.top + target.y
      }));
    }, point);
    const hover = page.locator('#hover');
    await page.waitForFunction(() => document.querySelector('#hover').textContent.trim().length > 0);
    assert.match((await hover.textContent()).trim(), /source/);
    const previousDetail = await detail.textContent();
    await canvas.evaluate((node, target) => {
      const rect = node.getBoundingClientRect();
      node.dispatchEvent(new MouseEvent('click', {
        bubbles: true, clientX: rect.left + target.x, clientY: rect.top + target.y
      }));
    }, point);
    await page.waitForFunction(previous => document.querySelector('#detail-message').textContent !== previous,
      previousDetail);
    assert.notEqual(await detail.textContent(), previousDetail,
      'clicking a different plotted point should change the selected frame');
    assert.ok((await detail.textContent()).includes('source ' + point.source),
      'chart selection should open details for the clicked source');
    assert.equal(errors.length, 0, errors.join('\\n'));
    console.log('Browser report smoke and chart/table interaction checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
