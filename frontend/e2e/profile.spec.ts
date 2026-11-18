import { test, expect } from '@playwright/test';

test('signed-in user sees their live identity and saved landing preference on profile', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/login');
  await page.getByLabel('Email address').fill(process.env.E2E_EMAIL || 'admin@ketsip.local');
  await page.getByLabel('Password').fill(process.env.E2E_NEW_PASSWORD || 'ChangedPassword456!');
  const loginResponse = page.waitForResponse(response => response.url().includes('/api/auth/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in' }).click();
  const response = await loginResponse;
  expect(response.status()).toBe(200);
  const { user } = await response.json();
  await page.getByRole('link', { name: 'My Profile' }).click();
  await expect(page.getByText(user.email, { exact: true })).toBeVisible();
  await expect(page.getByLabel('Default landing page')).toHaveValue(user.defaultLandingPage);
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  const dashboard = page.waitForResponse(response => response.url().includes('/api/dashboard/executive'));
  await page.reload();
  expect((await dashboard).status()).toBe(200);
  await page.getByRole('link', { name: 'My Profile' }).click();
  await expect(page.getByLabel('Default landing page')).toHaveValue(user.defaultLandingPage);
  expect(errors).toEqual([]);
});
