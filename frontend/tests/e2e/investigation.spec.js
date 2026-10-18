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
  await expect(page.getByRole('alert').first()).toBeVisible({ timeout: 20000 });
});

test('rate limiting surfaces an error rather than a success report', async ({ page }) => {
  await page.route('**/api/**', route => route.fulfill({
    status: 429, headers: {'retry-after':'15'},
    contentType: 'application/json', body: JSON.stringify({detail:'Rate limit exceeded'})
  }));
  await page.goto('/app/');
  await page.getByRole('textbox',{name:'Ethereum wallet address'}).fill('0x1111111111111111111111111111111111111111');
  await page.getByRole('button',{name:'Investigate wallet'}).click();
  await expect(page.getByRole('alert').first()).toBeVisible();
  await expect(page.getByRole('heading',{name:'What matters first'})).toHaveCount(1);
});

test('slow backend keeps an explicit loading state', async ({ page }) => {
  await page.route('**/api/**', async route => {
    await new Promise(resolve => setTimeout(resolve,1200));
    await route.fulfill({status:503, contentType:'application/json',body:JSON.stringify({detail:'Temporarily unavailable'})});
  });
  await page.goto('/app/');
  await page.getByRole('textbox',{name:'Ethereum wallet address'}).fill('0x1111111111111111111111111111111111111111');
  await page.getByRole('button',{name:'Investigate wallet'}).click();
  await expect(page.getByRole('button',{name:'Building intelligence…'})).toBeDisabled();
  await expect(page.getByRole('alert').first()).toBeVisible({timeout:20000});
});

test('bounded empty evidence remains an explicit empty state', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const url=route.request().url();
    if(url.includes('/indexed-graph'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({root:'0x1111111111111111111111111111111111111111',edges:[],nodes:[]})});
    if(url.includes('/fund-flow'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({directed_paths:[],token_flow:{available:false,assets:[],edges:[]},entity_exposures:[],flow_summary:{observed_incoming_wei:'0',observed_outgoing_wei:'0'}})});
    if(url.includes('/coverage-summary'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({coverage_grade:'bounded',coverage_statement:'Synthetic empty evidence fixture'})});
    return route.fulfill({status:200,contentType:'application/json',body:'{}'});
  });
  await page.goto('/app/');
  await page.getByRole('textbox',{name:'Ethereum wallet address'}).fill('0x1111111111111111111111111111111111111111');
  await page.getByRole('button',{name:'Investigate wallet'}).click();
  await expect(page.getByText('No graphable indexed transfers are currently available for this wallet.')).toBeVisible({timeout:30000});
});
