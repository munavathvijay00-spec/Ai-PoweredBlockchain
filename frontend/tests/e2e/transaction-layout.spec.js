import { test, expect } from '@playwright/test';

// Stable, evidence-shaped fixtures reveal CSS regressions without requiring a
// live RPC node or artificially changing production investigation records.
const tx = {
  hash: '0x' + 'a'.repeat(64),
  from_address: '0x' + '1'.repeat(40),
  to_address: '0x' + '2'.repeat(40),
  value_wei: '0',
  block_number: 26354001,
  timestamp: '2026-11-06T06:24:11Z',
  risk_score: 50,
  risk_factors: [{ factor: 'repeated_counterparty', reason: 'Counterparty concentration', points: 50 }],
};
async function mockMonitor(page) {
  await page.route('**/api/**', route => {
    const url = route.request().url();
    const payload = url.includes('/transaction-browser')
      ? { transactions: [tx, { ...tx, hash: '0x' + 'b'.repeat(64) }], total: 2, distribution: {} }
      : url.includes('/flagged') ? { transactions: [] } : {};
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
  await page.goto('/app/');
  await expect(page.getByRole('heading', { name: 'Transactions' })).toBeVisible();
  await expect(page.getByText('Showing 1–2 of 2 matching records')).toBeVisible();
}

test('wide workstation keeps transaction rows compact and action labels horizontal', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockMonitor(page);
  const table = page.getByRole('table');
  await expect(table).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(2);
  const measurements = await table.evaluate(tableElement => {
    const first = tableElement.querySelector('tbody tr');
    const button = first.querySelector('.cs-details-button');
    const bounds = button.getBoundingClientRect();
    const styles = getComputedStyle(button);
    const scrollRegion = tableElement.closest('.cs-transaction-scroll');
    return {
      rowHeight: first.getBoundingClientRect().height,
      buttonWidth: bounds.width,
      buttonHeight: bounds.height,
      whiteSpace: styles.whiteSpace,
      tableWidth: tableElement.getBoundingClientRect().width,
      scrollWidth: scrollRegion.clientWidth,
    };
  });
  expect(measurements.rowHeight).toBeLessThan(190);
  expect(measurements.buttonWidth).toBeGreaterThan(95);
  expect(measurements.buttonHeight).toBeLessThan(55);
  expect(measurements.whiteSpace).toBe('nowrap');
  expect(measurements.tableWidth).toBeGreaterThanOrEqual(1050);
});

test('medium workstation switches to readable transaction cards without horizontal document overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 850 });
  await mockMonitor(page);
  await expect(page.getByRole('table')).toBeHidden();
  const cards = page.locator('.cs-transaction-mobile article');
  await expect(cards).toHaveCount(2);
  await expect(cards.first().getByRole('button', { name: 'View details' })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
});
