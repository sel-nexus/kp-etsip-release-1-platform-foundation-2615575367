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
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'POST') return json({ id: 'new' }, 201);
    if (String(url).includes('/users')) return json(page([]));
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

it('allows auditors to filter audit events without administrative controls', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page([{ id: 'a1', timestamp: '2026-01-01T00:00:00Z', userName: 'Pat', action: 'edit', entityType: 'user', details: 'User updated' }])));
  render(<MemoryRouter><Administration user={{ ...admin, role: 'Auditor' }} /></MemoryRouter>);
  expect(await screen.findByText('User updated')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Users' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Roles' })).not.toBeInTheDocument();
  await userEvent.setup().selectOptions(screen.getByLabelText('Action'), 'edit');
  expect(fetcher.mock.calls.some(([url]) => String(url).includes('action=edit'))).toBe(true);
});
