import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('executive logs in, reviews filtered metrics and exports a portfolio report', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/login');
  await page.getByLabel('Email address').fill(process.env.E2E_EMAIL || 'admin@ketsip.local');
  await page.getByLabel('Password').fill(process.env.E2E_NEW_PASSWORD || 'ChangedPassword456!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('link', { name: 'Applications', exact: true })).toBeVisible();
  const adminToken = await page.evaluate(() => sessionStorage.getItem('ketsip.token'));
  expect(adminToken).toBeTruthy();
  const headers = { Authorization: `Bearer ${adminToken}` };
  const email = `journey-executive-${Date.now()}@example.com`;
  const initial = 'InitialPassword123!';
  const replacement = 'ChangedPassword456!';
  const created = await request.post('/api/users', { headers, data: { name: 'Journey Executive', email, password: initial, role: 'Executive', portfolioAccess: [], status: 'Active', managerName: null, vendorIndicator: false } });
  expect(created.status()).toBe(201);
  const account = await created.json();
  try {
    await page.getByRole('button', { name: 'Sign out' }).click();
    await page.getByLabel('Email address').fill(email);
    await page.getByLabel('Password').fill(initial);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText(/change your initial password/i)).toBeVisible();
    await page.getByLabel('Current password').fill(initial);
    await page.getByLabel('New password').fill(replacement);
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByText('Password changed. Please sign in again.')).toBeVisible();
    await page.getByLabel('Email address').fill(email);
    await page.getByLabel('Password').fill(replacement);
    const loginPromise = page.waitForResponse(response => response.url().includes('/api/auth/login') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in' }).click();
    const login = await loginPromise;
    expect(login.status()).toBe(200);
    expect((await login.json()).user.role).toBe('Executive');
    await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
    await page.getByLabel('Portfolio').selectOption({ label: 'Payments' });
    const dashboardPromise = page.waitForResponse(response => response.url().includes('/dashboard/executive?') && response.url().includes('riskLevel=High'));
    await page.getByLabel('Risk level').selectOption('High');
    const dashboard = await dashboardPromise;
    expect(dashboard.status()).toBe(200);
    const data = await dashboard.json();
    await expect(page.locator('.insight-metric').filter({ hasText: 'Total Applications' })).toContainText(String(data.totalApplications));
    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    const reportPromise = page.waitForResponse(response => response.url().includes('/api/reports/portfolios?') && !response.url().includes('format=csv'));
    await page.getByLabel('Report').selectOption('portfolios');
    const report = await reportPromise;
    expect(report.status()).toBe(200);
    const reportData = await report.json();
    expect(reportData.items.some((item: { name: string }) => item.name === 'Payments')).toBe(true);
    await expect(page.getByRole('link', { name: 'Payments', exact: true })).toBeVisible();
    const csvPromise = page.waitForResponse(response => response.url().includes('/api/reports/portfolios?') && response.url().includes('format=csv'));
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export CSV' }).click();
    const csv = await csvPromise;
    expect(csv.status()).toBe(200);
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe('portfolios.csv');
    expect(await readFile(await download.path(), 'utf8')).toContain('Payments');
    expect(errors).toEqual([]);
  } finally {
    const removed = await request.delete(`/api/users/${account.id}`, { headers });
    expect(removed.status()).toBe(204);
  }
});

for (const role of ['Portfolio Leader', 'Auditor'] as const) {
  test(`${role} sees authorized inventory and governance controls`, async ({ page, request }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.goto('/login');
    await page.getByLabel('Email address').fill(process.env.E2E_EMAIL || 'admin@ketsip.local');
    await page.getByLabel('Password').fill(process.env.E2E_NEW_PASSWORD || 'ChangedPassword456!');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('link', { name: 'Applications', exact: true })).toBeVisible();
    const adminToken = await page.evaluate(() => sessionStorage.getItem('ketsip.token'));
    const headers = { Authorization: `Bearer ${adminToken}` };
    const portfolioResponse = await request.get('/api/portfolios?limit=100', { headers });
    expect(portfolioResponse.status()).toBe(200);
    const portfolios = (await portfolioResponse.json()).items;
    const payments = portfolios.find((p: { name: string }) => p.name === 'Payments');
    expect(payments).toBeTruthy();
    const email = `journey-${Date.now()}-${role === 'Auditor' ? 'audit' : 'leader'}@example.com`;
    const initial = 'InitialPassword123!';
    const replacement = 'ChangedPassword456!';
    const created = await request.post('/api/users', { headers, data: { name: `Journey ${role}`, email, password: initial, role, portfolioAccess: role === 'Portfolio Leader' ? [payments.id] : [], status: 'Active', managerName: null, vendorIndicator: false } });
    expect(created.status()).toBe(201);
    const account = await created.json();
    let originalApplication: Record<string, unknown> | null = null;
    let outsideApplication: Record<string, unknown> | null = null;
    let restoreApplication = false;
    try {
      if (role === 'Portfolio Leader') {
        const inventory = await request.get('/api/applications?limit=100', { headers });
        expect(inventory.status()).toBe(200);
        const items = (await inventory.json()).items;
        originalApplication = items.find((item: { name: string }) => item.name === 'Payment Gateway') ?? null;
        outsideApplication = items.find((item: { portfolioId: string }) => item.portfolioId && item.portfolioId !== payments.id) ?? null;
        expect(originalApplication).toBeTruthy();
        expect(outsideApplication).toBeTruthy();
        expect(originalApplication?.portfolioId).toBe(payments.id);
        expect(outsideApplication?.portfolioId).not.toBe(payments.id);
      }
      await page.getByRole('button', { name: 'Sign out' }).click();
      await page.getByLabel('Email address').fill(email);
      await page.getByLabel('Password').fill(initial);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect(page.getByText(/change your initial password/i)).toBeVisible();
      await page.getByLabel('Current password').fill(initial);
      await page.getByLabel('New password').fill(replacement);
      await page.getByRole('button', { name: 'Change password' }).click();
      await expect(page.getByText('Password changed. Please sign in again.')).toBeVisible();
      await page.getByLabel('Email address').fill(email);
      await page.getByLabel('Password').fill(replacement);
      const roleLoginPromise = page.waitForResponse(response => response.url().includes('/api/auth/login') && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Sign in' }).click();
      const roleLogin = await roleLoginPromise;
      expect(roleLogin.status()).toBe(200);
      expect((await roleLogin.json()).user.role).toBe(role);
      await page.getByRole('link', { name: 'Applications', exact: true }).click();
      await expect(page.getByRole('link', { name: 'Payment Gateway', exact: true })).toBeVisible();
      if (role === 'Portfolio Leader') {
        await expect(page.getByRole('link', { name: String(outsideApplication!.name), exact: true })).toHaveCount(0);
        await page.getByRole('link', { name: 'Payment Gateway', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Edit application' })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Delete application' })).toHaveCount(0);
        await expect(page.getByRole('link', { name: 'Administration' })).toHaveCount(0);
        const leaderToken = await page.evaluate(() => sessionStorage.getItem('ketsip.token'));
        expect(leaderToken).toBeTruthy();
        const leaderHeaders = { Authorization: `Bearer ${leaderToken}` };
        const owner = `Leader journey ${Date.now()}`;
        await page.getByRole('button', { name: 'Edit application' }).click();
        await page.getByLabel('Business owner').fill(owner);
        const savePromise = page.waitForResponse(response => response.url().endsWith(`/api/applications/${originalApplication!.id}`) && response.request().method() === 'PUT');
        restoreApplication = true;
        await page.getByRole('button', { name: 'Save application' }).click();
        const saved = await savePromise;
        expect(saved.status()).toBe(200);
        expect((await saved.json()).businessOwner).toBe(owner);
        await expect(page.getByText(owner, { exact: true })).toBeVisible();
        await page.reload();
        await expect(page.getByText(owner, { exact: true })).toBeVisible();
        const reread = await request.get(`/api/applications/${originalApplication!.id}`, { headers: leaderHeaders });
        expect(reread.status()).toBe(200);
        expect((await reread.json()).businessOwner).toBe(owner);

        const outsideRead = await request.get(`/api/applications/${outsideApplication!.id}`, { headers: leaderHeaders });
        expect(outsideRead.status()).toBe(403);
        const { id: outsideId, portfolioName: outsidePortfolio, createdAt: outsideCreated, updatedAt: outsideUpdated, ...outsideFields } = outsideApplication!;
        const deniedEdit = await request.put(`/api/applications/${outsideId}`, { headers: leaderHeaders, data: { ...outsideFields, businessOwner: owner } });
        expect(deniedEdit.status()).toBe(403);
        const outsideReread = await request.get(`/api/applications/${outsideId}`, { headers });
        expect(outsideReread.status()).toBe(200);
        expect((await outsideReread.json()).businessOwner).toBe(outsideApplication!.businessOwner);
      } else {
        await page.getByRole('link', { name: 'Administration' }).click();
        await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Users' })).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Roles' })).toHaveCount(0);
        await expect(page.getByRole('table')).toBeVisible();
      }
      await page.getByRole('link', { name: 'Reports', exact: true }).click();
      await expect(page.getByRole('link', { name: 'Payment Gateway', exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Export CSV' })).toBeVisible();
      expect(errors).toEqual([]);
    } finally {
      try {
        if (restoreApplication && originalApplication) {
          const { id, portfolioName, createdAt, updatedAt, ...fields } = originalApplication;
          const restored = await request.put(`/api/applications/${id}`, { headers, data: fields });
          expect(restored.status()).toBe(200);
        }
      } finally {
        const removed = await request.delete(`/api/users/${account.id}`, { headers });
        expect(removed.status()).toBe(204);
      }
    }
  });
}

test('read-only account can view reports but has no export control', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/login');
  await page.getByLabel('Email address').fill(process.env.E2E_EMAIL || 'admin@ketsip.local');
  await page.getByLabel('Password').fill(process.env.E2E_NEW_PASSWORD || 'ChangedPassword456!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('link', { name: 'Applications', exact: true })).toBeVisible();
  const adminToken = await page.evaluate(() => sessionStorage.getItem('ketsip.token'));
  expect(adminToken).toBeTruthy();
  const headers = { Authorization: `Bearer ${adminToken}` };
  const email = `journey-readonly-${Date.now()}@example.com`;
  const initial = 'InitialPassword123!';
  const replacement = 'ChangedPassword456!';
  const created = await request.post('/api/users', { headers, data: { name: 'Journey Read Only', email, password: initial, role: 'Read Only', portfolioAccess: [], status: 'Active', managerName: null, vendorIndicator: false } });
  expect(created.status()).toBe(201);
  const account = await created.json();
  try {
    await page.getByRole('button', { name: 'Sign out' }).click();
    await page.getByLabel('Email address').fill(email);
    await page.getByLabel('Password').fill(initial);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText(/change your initial password/i)).toBeVisible();
    await page.getByLabel('Current password').fill(initial);
    await page.getByLabel('New password').fill(replacement);
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByText('Password changed. Please sign in again.')).toBeVisible();
    await page.getByLabel('Email address').fill(email);
    await page.getByLabel('Password').fill(replacement);
    const loginPromise = page.waitForResponse(response => response.url().includes('/api/auth/login') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in' }).click();
    const login = await loginPromise;
    expect(login.status()).toBe(200);
    expect((await login.json()).user.role).toBe('Read Only');
    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export CSV' })).toHaveCount(0);
    await expect(page.getByRole('table')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    const removed = await request.delete(`/api/users/${account.id}`, { headers });
    expect(removed.status()).toBe(204);
  }
});
