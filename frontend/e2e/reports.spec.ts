import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('mobile user sees loading, live dashboard data, and both report exports', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/login');
  await page.getByLabel('Email address').fill(process.env.E2E_EMAIL || 'admin@ketsip.local');
  await page.getByLabel('Password').fill(process.env.E2E_NEW_PASSWORD || 'ChangedPassword456!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('link', { name: 'My Profile' }).click();

  // Record even a brief loading state without delaying or replacing the live request.
  await page.evaluate(() => {
    const observer = new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) {
        if (node instanceof Element && (node.matches('[role="status"]') ? node : node.querySelector('[role="status"]'))?.textContent === 'Loading dashboard…') {
          document.documentElement.dataset.dashboardLoadingObserved = 'true';
          observer.disconnect();
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });
  const dashboardResponse = page.waitForResponse(response => response.url().includes('/api/dashboard/executive'));
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  const dashboard = await dashboardResponse;
  expect(dashboard.status()).toBe(200);
  await expect(page.locator('html')).toHaveAttribute('data-dashboard-loading-observed', 'true');
  const metrics = await dashboard.json();
  await expect(page.locator('.insight-metric').filter({ hasText: 'Total Applications' })).toContainText(String(metrics.totalApplications));
  await page.screenshot({ path: testInfo.outputPath('mobile-dashboard.png'), fullPage: true });

  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  for (const kind of ['applications', 'portfolios'] as const) {
    const responsePromise = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === `/api/reports/${kind}` && url.searchParams.get('riskLevel') === 'High' && !url.searchParams.has('format');
    });
    if (kind === 'portfolios') await page.getByLabel('Report').selectOption(kind);
    else {
      // Trigger a request after listeners are installed even if navigation loaded quickly.
      await page.getByLabel('Risk level').selectOption('High');
    }
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const data = await response.json();
    if (data.items.length) {
      const link = page.getByRole('link', { name: data.items[0].name, exact: true });
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute('href', `/${kind}/${data.items[0].id}`);
    }
    else await expect(page.getByText('No records match these filters.')).toBeVisible();
    const csvResponse = page.waitForResponse(response => response.url().includes(`/api/reports/${kind}?`) && response.url().includes('format=csv'));
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export CSV' }).click();
    const csv = await csvResponse;
    expect(csv.status()).toBe(200);
    const file = await download;
    expect(file.suggestedFilename()).toBe(`${kind}.csv`);
    const content = await readFile(await file.path(), 'utf8');
    expect(content).toContain('name,');
    if (data.items.length) expect(content).toContain(data.items[0].name);
  }
  await page.screenshot({ path: testInfo.outputPath('mobile-report.png'), fullPage: true });
  await page.getByLabel('Risk level').selectOption('');
  await page.getByRole('link', { name: 'Payments', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Payments' })).toBeVisible();
  await expect(page.getByText('Demonstration portfolio')).toBeVisible();
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('link', { name: 'Payments', exact: true }).click();
  await expect(page.getByText('Demonstration portfolio')).toBeVisible();
  expect(errors).toEqual([]);
});
