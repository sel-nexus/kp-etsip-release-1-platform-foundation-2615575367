import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Administration from './Administration';
import type { User } from '../types';

const admin: User = { id: 'admin', name: 'Admin', email: 'admin@example.com', role: 'Administrator', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: false };
const page = (items: unknown[]) => ({ items, total: items.length, offset: 0, limit: 25 });
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
afterEach(() => { cleanup(); vi.restoreAllMocks(); sessionStorage.clear(); });

it('creates a user with a role and assigned portfolio', async () => {
  let created = false;
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'POST') { created = true; return json({ id: 'new' }, 201); }
    if (String(url).includes('/users')) return json(page(created ? [{ id: 'new', name: 'Pat', email: 'pat@example.com', role: 'Portfolio Leader', portfolioAccess: ['p1'], status: 'Active', managerName: null, vendorIndicator: false }] : []));
    if (String(url).includes('/portfolios')) return json(page([{ id: 'p1', name: 'Payments' }]));
    return json(page([]));
  });
  render(<MemoryRouter initialEntries={['/administration?tab=users']}><Administration user={admin} /></MemoryRouter>);
  const actor = userEvent.setup();
  await actor.click(screen.getByRole('button', { name: 'Create user' }));
  await actor.type(screen.getByLabelText('Name'), 'Pat');
  await actor.type(screen.getByLabelText('Email'), 'pat@example.com');
  await actor.type(screen.getByLabelText('Initial password'), 'ValidPassword123!');
  await actor.selectOptions(screen.getByLabelText('Role'), 'Portfolio Leader');
  await actor.click(await screen.findByLabelText('Payments'));
  await actor.click(screen.getByRole('button', { name: 'Save user' }));
  expect(await screen.findByText('User saved.')).toBeInTheDocument();
  const posted = fetcher.mock.calls.find(([, options]) => options?.method === 'POST');
  expect(JSON.parse(String(posted?.[1]?.body))).toMatchObject({ name: 'Pat', role: 'Portfolio Leader', portfolioAccess: ['p1'] });
  expect(await screen.findByText('pat@example.com')).toBeInTheDocument();
  expect(screen.getByText('Portfolio Leader')).toBeInTheDocument();
});

it('limits role permissions and displays server errors', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
    if (options?.method === 'PUT') return json({ detail: 'Permission denied' }, 403);
    return json(page([{ id: 'r1', name: 'Auditor', description: 'Audit', permissions: ['view', 'export'] }]));
  });
  render(<MemoryRouter initialEntries={['/administration?tab=roles']}><Administration user={admin} /></MemoryRouter>);
  const actor = userEvent.setup();
  await actor.click(await screen.findByRole('button', { name: 'Edit Auditor' }));
  expect(screen.getByLabelText('administer')).toBeDisabled();
  await actor.click(screen.getByLabelText('export'));
  await actor.click(screen.getByRole('button', { name: 'Save role' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
});

it('clears stale role permissions after a failed reload and shows fresh permissions on retry', async () => {
  const original = { id: 'r1', name: 'Auditor', description: 'Audit', permissions: ['view', 'export'] };
  const refreshed = { ...original, permissions: ['view'] };
  let attempts = 0;
  let finishReload!: (response: Response) => void;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
    if (String(url).includes('/roles')) {
      attempts += 1;
      if (attempts === 1) return json(page([original]));
      if (attempts === 2) return new Promise<Response>(resolve => { finishReload = resolve; });
      return json(page([refreshed]));
    }
    return json(page([]));
  });
  render(<MemoryRouter initialEntries={['/administration?tab=roles']}><Administration user={admin} /></MemoryRouter>);
  const actor = userEvent.setup();
  expect(await screen.findByText('view, export')).toBeVisible();
  await actor.click(screen.getByRole('button', { name: 'Edit Auditor' }));
  expect(screen.getByLabelText('export')).toBeChecked();

  await actor.click(screen.getByRole('button', { name: 'Audit log' }));
  await actor.click(screen.getByRole('button', { name: 'Roles' }));
  expect(screen.getByText('Loading…')).toBeVisible();
  expect(screen.queryByText('view, export')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('export')).not.toBeInTheDocument();
  finishReload(json({ detail: 'Roles reload failed' }, 500));
  expect(await screen.findByRole('alert')).toHaveTextContent('Roles reload failed');
  expect(screen.queryByText('view, export')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Edit Auditor' })).not.toBeInTheDocument();
  expect(screen.queryByLabelText('export')).not.toBeInTheDocument();

  await actor.click(screen.getByRole('button', { name: 'Audit log' }));
  await actor.click(screen.getByRole('button', { name: 'Roles' }));
  await actor.click(await screen.findByRole('button', { name: 'Edit Auditor' }));
  expect(screen.getByLabelText('view')).toBeChecked();
  expect(screen.getByLabelText('export')).not.toBeChecked();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('clears stale users and pagination after a failed search, then displays a successful retry', async () => {
  const original = { id: 'u1', name: 'Original User', email: 'original@example.com', role: 'Engineer', portfolioAccess: [], status: 'Active', managerName: null, vendorIndicator: false };
  const match = { ...original, id: 'u2', name: 'Matching User', email: 'match@example.com' };
  let filteredAttempts = 0;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
    const path = String(url);
    if (path.includes('/users')) {
      if (path.includes('search=x')) {
        filteredAttempts += 1;
        return filteredAttempts === 1 ? json({ detail: 'User search failed' }, 500) : json(page([match]));
      }
      return json(page([original]));
    }
    return json(page([]));
  });
  render(<MemoryRouter initialEntries={['/administration?tab=users']}><Administration user={admin} /></MemoryRouter>);
  const actor = userEvent.setup();
  expect(await screen.findByText('original@example.com')).toBeVisible();
  expect(screen.getByText('Showing 1–1 of 1')).toBeVisible();

  await actor.type(screen.getByLabelText('Search users'), 'x');
  expect(await screen.findByRole('alert')).toHaveTextContent('User search failed');
  expect(screen.queryByText('original@example.com')).not.toBeInTheDocument();
  expect(screen.queryByText('Showing 1–1 of 1')).not.toBeInTheDocument();
  expect(screen.queryByText('No users found.')).not.toBeInTheDocument();

  await actor.click(screen.getByRole('button', { name: 'Audit log' }));
  await actor.click(screen.getByRole('button', { name: 'Users' }));
  expect(await screen.findByText('match@example.com')).toBeVisible();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.getByText('Showing 1–1 of 1')).toBeVisible();
});

it('clears stale audit events and pagination after a failed filter, then displays a successful retry', async () => {
  const original = { id: 'a1', timestamp: '2026-01-01T00:00:00Z', userName: 'Pat', action: 'edit', entityType: 'user', details: 'Original event' };
  const match = { ...original, id: 'a2', action: 'delete', details: 'Matching event' };
  let filteredAttempts = 0;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
    const path = String(url);
    if (path.includes('/audit-logs')) {
      if (path.includes('action=delete')) {
        filteredAttempts += 1;
        return filteredAttempts === 1 ? json({ detail: 'Audit filter failed' }, 500) : json(page([match]));
      }
      return json(page([original]));
    }
    return json(page([]));
  });
  render(<MemoryRouter><Administration user={admin} /></MemoryRouter>);
  const actor = userEvent.setup();
  expect(await screen.findByText('Original event')).toBeVisible();
  expect(screen.getByText('Showing 1–1 of 1')).toBeVisible();

  await actor.selectOptions(screen.getByLabelText('Action'), 'delete');
  expect(await screen.findByRole('alert')).toHaveTextContent('Audit filter failed');
  expect(screen.queryByText('Original event')).not.toBeInTheDocument();
  expect(screen.queryByText('Showing 1–1 of 1')).not.toBeInTheDocument();
  expect(screen.queryByText('No audit events match these filters.')).not.toBeInTheDocument();

  await actor.click(screen.getByRole('button', { name: 'Roles' }));
  await actor.click(screen.getByRole('button', { name: 'Audit log' }));
  expect(await screen.findByText('Matching event')).toBeVisible();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.getByText('Showing 1–1 of 1')).toBeVisible();
});

it('allows auditors to filter audit events without administrative controls', async () => {
  const event = { id: 'a1', timestamp: '2026-01-01T00:00:00Z', userName: 'Pat', action: 'edit', entityType: 'user', details: 'User updated' };
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async url => json(page(String(url).includes('action=delete') ? [] : [event])));
  render(<MemoryRouter><Administration user={{ ...admin, role: 'Auditor' }} /></MemoryRouter>);
  expect(await screen.findByText('User updated')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Users' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Roles' })).not.toBeInTheDocument();
  await userEvent.setup().selectOptions(screen.getByLabelText('Action'), 'delete');
  expect(fetcher.mock.calls.some(([url]) => String(url).includes('action=delete'))).toBe(true);
  expect(await screen.findByText('No audit events match these filters.')).toBeInTheDocument();
});
