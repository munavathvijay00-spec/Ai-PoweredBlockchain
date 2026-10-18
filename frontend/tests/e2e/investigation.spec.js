import { test, expect } from '@playwright/test';

test('investigation home, validation, and workspace navigation', async ({ page }) => {
  await page.goto('/app/');
  await expect(page.getByRole('heading', { name: 'One wallet. One evidence trail.' })).toBeVisible();
  await page.getByRole('button', { name: 'Investigate wallet' }).click();
  await expect(page.getByRole('alert')).toContainText('valid Ethereum address');
  await page.getByRole('button', { name: 'Monitor', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Product workspace' }).getByRole('button', { name: 'Monitor' })).toHaveAttribute('aria-current', 'page');
  await page.getByRole('button', { name: 'Cases', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Product workspace' }).getByRole('button', { name: 'Cases' })).toHaveAttribute('aria-current', 'page');
  await page.getByRole('button', { name: 'Investigate', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'One wallet. One evidence trail.' })).toBeVisible();
});

test('graceful investigation failure never claims completed evidence', async ({ page }) => {
  await page.route('**/api/**', async route => {
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Investigation capacity is busy' }) });
  });
  await page.goto('/app/');
  await page.getByRole('textbox', { name: 'Ethereum wallet address' }).fill('0x1111111111111111111111111111111111111111');
  await page.getByRole('button', { name: 'Investigate wallet' }).click();
  await expect(page.getByRole('alert')).toBeVisible({ timeout: 20000 });
});
