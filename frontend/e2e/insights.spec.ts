import { test, expect } from '@playwright/test';

test('executive reviews filtered metrics and exports a portfolio report', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/login');
  await page.getByLabel('Email address').fill(process.env.E2E_EMAIL || 'admin@ketsip.local');
  await page.getByLabel('Password').fill(process.env.E2E_NEW_PASSWORD || 'ChangedPassword456!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await page.getByLabel('Portfolio').selectOption({ label: 'Payments' });
  const dashboardPromise = page.waitForResponse(response => response.url().includes('/dashboard/executive?') && response.url().includes('riskLevel=High') && response.status() === 200);
  await page.getByLabel('Risk level').selectOption('High');
  const dashboard = await dashboardPromise;
  const data = await dashboard.json();
  await expect(page.locator('.insight-metric').filter({ hasText: 'Total Applications' })).toContainText(String(data.totalApplications));
  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  await page.getByLabel('Report').selectOption('portfolios');
  await expect(page.getByRole('link', { name: 'Payments', exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  expect((await downloadPromise).suggestedFilename()).toBe('portfolios.csv');
  expect(errors).toEqual([]);
});

test('read-only account can view reports but has no export control', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/login');
  await page.getByLabel('Email address').fill(process.env.E2E_READONLY_EMAIL || 'readonly@ketsip.local');
  await page.getByLabel('Password').fill(process.env.E2E_READONLY_PASSWORD || 'ChangedPassword456!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export CSV' })).toHaveCount(0);
  await expect(page.getByRole('table')).toBeVisible();
  expect(errors).toEqual([]);
});
