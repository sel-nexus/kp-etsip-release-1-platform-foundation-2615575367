import { test, expect } from '@playwright/test';

test('stored application payload remains literal in inventory, detail, report and audit', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const marker = `xss-${Date.now()}`;
  const payload = `<img src=x onerror="window.__storedXss=1" data-xss="${marker}">`;
  await page.addInitScript(() => { (window as unknown as { __storedXss: number }).__storedXss = 0; });
  await page.goto('/login');
  await page.getByLabel('Email address').fill(process.env.E2E_EMAIL || 'admin@ketsip.local');
  await page.getByLabel('Password').fill(process.env.E2E_NEW_PASSWORD || 'ChangedPassword456!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('link', { name: 'Applications', exact: true })).toBeVisible();
  const token = await page.evaluate(() => sessionStorage.getItem('ketsip.token'));
  expect(token).toBeTruthy();
  const headers = { Authorization: `Bearer ${token}` };
  const portfolios = await request.get('/api/portfolios?limit=100', { headers });
  expect(portfolios.status()).toBe(200);
  const portfolio = (await portfolios.json()).items.find((item: { name: string }) => item.name === 'Payments');
  expect(portfolio).toBeTruthy();
  const created = await request.post('/api/applications', { headers, data: {
    name: payload, description: payload, portfolioId: portfolio.id, productArea: payload,
    criticality: 'Medium', tier: 1, lifecycleStatus: 'Active', applicationHealthScore: 0,
    qualityScore: 0, automationCoverage: 0, unitTestCoverage: 0, openDefects: 0,
    openCriticalDefects: 0, riskLevel: 'Low',
  } });
  expect(created.status()).toBe(201);
  const item = await created.json();
  expect(item.name).toBe(payload);
  expect(item.description).toBe(payload);
  try {
    const stored = await request.get(`/api/applications/${item.id}`, { headers });
    expect(stored.status()).toBe(200);
    expect((await stored.json()).description).toBe(payload);
    const assertSafe = async () => {
      await expect(page.locator(`[data-xss="${marker}"]`)).toHaveCount(0);
      expect(await page.evaluate(() => (window as unknown as { __storedXss: number }).__storedXss)).toBe(0);
    };
    await page.getByRole('link', { name: 'Applications', exact: true }).click();
    await page.getByLabel('Search').fill(marker);
    await expect(page.getByRole('link', { name: payload, exact: true })).toBeVisible();
    await assertSafe();
    await page.getByRole('link', { name: payload, exact: true }).click();
    await expect(page.getByRole('heading', { name: payload })).toBeVisible();
    for (const field of ['Name', 'Description', 'Product area']) {
      const value = page.locator('dt').filter({ hasText: new RegExp(`^${field}$`) }).locator('..').locator('dd');
      await expect(value).toHaveText(payload);
    }
    await assertSafe();
    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    await page.getByLabel('Product area').fill(payload);
    await expect(page.getByRole('link', { name: payload, exact: true })).toBeVisible();
    const row = page.getByRole('row').filter({ has: page.getByRole('link', { name: payload, exact: true }) });
    await expect(row.locator('td').nth(2)).toHaveText(payload);
    await assertSafe();
    await page.getByRole('link', { name: 'Administration' }).click();
    await page.getByLabel('Action').selectOption('create');
    await expect(page.getByRole('cell', { name: `Application create: ${payload}`, exact: true })).toBeVisible();
    await assertSafe();
    expect(errors).toEqual([]);
  } finally {
    const deleted = await request.delete(`/api/applications/${item.id}`, { headers });
    expect(deleted.status()).toBe(204);
  }
});
