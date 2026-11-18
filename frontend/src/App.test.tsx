import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import type { User } from './types';

const user: User = { id: 'u', name: 'Test User', email: 'test@example.com', role: 'Engineer', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: false };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
beforeEach(() => { sessionStorage.clear(); window.history.replaceState({}, '', '/'); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('redirects anonymous protected navigation to sign in', async () => {
  window.history.replaceState({}, '', '/administration');
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  expect(window.location.pathname).toBe('/login');
});

it('restores a persisted identity before displaying its protected page', async () => {
  sessionStorage.setItem('ketsip.token', 'saved');
  window.history.replaceState({}, '', '/profile');
  let resolve!: (response: Response) => void;
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>(r => { resolve = r; }));
  render(<App />);
  expect(screen.getByText('Restoring session…')).toBeInTheDocument();
  await act(async () => resolve(json(user)));
  expect(await screen.findByText('test@example.com')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'My Profile' })).toBeInTheDocument();
});

it('clears a session that cannot be restored and shows a notice', async () => {
  sessionStorage.setItem('ketsip.token', 'invalid');
  window.history.replaceState({}, '', '/profile');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Unavailable' }, 503));
  render(<App />);
  expect(await screen.findByText('Unable to restore your session. Sign in again.')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  expect(sessionStorage.getItem('ketsip.token')).toBeNull();
});

it('forces initial password changes before protected pages', async () => {
  sessionStorage.setItem('ketsip.token', 'saved');
  window.history.replaceState({}, '', '/applications');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...user, mustChangePassword: true }));
  render(<App />);
  await waitFor(() => {
    expect(screen.getByRole('heading', { name: 'My Profile' })).toBeInTheDocument();
    expect(screen.getByText(/change your initial password/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe('/profile');
  });
  expect(screen.queryByRole('link', { name: 'Applications' })).not.toBeInTheDocument();
});

it('denies administration to an engineer', async () => {
  sessionStorage.setItem('ketsip.token', 'saved');
  window.history.replaceState({}, '', '/administration');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(user));
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
});

it.each([true, false])('signs out locally when server logout succeeds=%s', async success => {
  sessionStorage.setItem('ketsip.token', 'saved');
  window.history.replaceState({}, '', '/profile');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => options?.method === 'POST' ? json(success ? { status: 'ok' } : { detail: 'Unavailable' }, success ? 200 : 503) : json(user));
  render(<App />);
  await screen.findByText('test@example.com');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  expect(sessionStorage.getItem('ketsip.token')).toBeNull();
  if (!success) expect(screen.getByText('Session cleared locally; server sign-out could not be confirmed.')).toBeInTheDocument();
});

it.each([
  { role: 'Engineer', landing: null, expected: '/applications', mustChange: false },
  { role: 'Engineer', landing: 'dashboard', expected: '/profile', mustChange: true },
] as const)('routes a signed-in $role to $expected when password change is $mustChange', async ({ role, landing, expected, mustChange }) => {
  const identity = { ...user, role, defaultLandingPage: landing, mustChangePassword: mustChange };
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
    if (String(url).includes('/auth/login')) return json({ token: 'new-token', user: identity });
    if (String(url).includes('/auth/me')) return json(identity);
    if (String(url).includes('/portfolios')) return json({ items: [], total: 0, offset: 0, limit: 25 });
    return json({ items: [], total: 0, offset: 0, limit: 25 });
  });
  window.history.replaceState({}, '', '/login');
  render(<App />);
  const actor = userEvent.setup();
  await actor.type(screen.getByLabelText('Email address'), user.email);
  await actor.type(screen.getByLabelText('Password'), 'password');
  await actor.click(screen.getByRole('button', { name: 'Sign in' }));
  if (mustChange) {
    await waitFor(() => {
      expect(screen.getByText(/change your initial password/i)).toBeInTheDocument();
      expect(window.location.pathname).toBe(expected);
    });
  } else {
    expect(await screen.findByRole('heading', { name: 'Application Repository' })).toBeInTheDocument();
    expect(window.location.pathname).toBe(expected);
  }
  expect(sessionStorage.getItem('ketsip.token')).toBe('new-token');
});

it('responds to an expired-session event by returning to login', async () => {
  sessionStorage.setItem('ketsip.token', 'saved');
  window.history.replaceState({}, '', '/profile');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(user));
  render(<App />);
  await screen.findByText('test@example.com');
  act(() => window.dispatchEvent(new Event('session-expired')));
  expect(await screen.findByText('Your session has expired. Sign in again.')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
});
