import { test, expect } from '@playwright/test';

test('anonymous protected route redirects to sign-in and invalid credentials are rejected by the server', async ({ page }, testInfo) => {
  const errors: string[] = [];
  const consoleErrors: { text: string; url: string }[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push({ text: message.text(), url: message.location().url }); });
  await page.goto('/administration');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Administration' })).toHaveCount(0);
  await page.getByLabel('Email address').fill('unknown-e2e@example.com');
  await page.getByLabel('Password').fill('incorrect-password');
  const responsePromise = page.waitForResponse(response => response.url().includes('/api/auth/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(401);
  const body = await response.json();
  await expect(page.getByRole('alert')).toHaveText(body.detail);
  await expect(page).toHaveURL(/\/login$/);
  await page.screenshot({ path: testInfo.outputPath('invalid-login.png'), fullPage: true });
  // Allow at most one Chromium resource error for this exact rejected login.
  const loginUrl = new URL('/api/auth/login', page.url()).href;
  const expected = consoleErrors.findIndex(message => message.url === loginUrl && /^Failed to load resource: the server responded with a status of 401(?: \(Unauthorized\))?$/.test(message.text));
  if (expected !== -1) consoleErrors.splice(expected, 1);
  expect(errors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
