import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Portfolios from './Portfolios';
import PortfolioDetail from './PortfolioDetail';
import type { User } from '../types';

const admin: User = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'Administrator', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: false };
const portfolio = { id: 'p1', name: 'Payments', owner: 'Alex', productArea: 'Commerce', description: 'Payment services', status: 'Active', applicationCount: 1, qualityScore: 80, createdAt: '', updatedAt: '' };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
afterEach(() => { cleanup(); vi.restoreAllMocks(); sessionStorage.clear(); });

it('filters the inventory and creates a complete portfolio', async () => {
  let created = false;
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
    if (options?.method === 'POST') { created = true; return json({ ...portfolio, name: 'Payments New' }, 201); }
    const items = created ? [portfolio, { ...portfolio, id: 'p2', name: 'Payments New' }] : [portfolio];
    return json({ items, total: items.length, offset: 0, limit: 25 });
  });
  render(<MemoryRouter><Portfolios user={admin} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Payments' })).toBeInTheDocument();
  const actor = userEvent.setup();
  await actor.type(screen.getByLabelText('Search'), 'Pay');
  expect(fetcher.mock.calls.some(([url]) => String(url).includes('search=Pay'))).toBe(true);
  await actor.click(screen.getByRole('button', { name: 'Create portfolio' }));
  await actor.type(screen.getByLabelText('Name *'), 'Payments New');
  await actor.type(screen.getByLabelText('Owner'), 'Alex');
  await actor.type(screen.getByLabelText('Product area'), 'Commerce');
  await actor.type(screen.getByLabelText('Description'), 'Payment services');
  await actor.click(screen.getByRole('button', { name: 'Save portfolio' }));
  expect(fetcher.mock.calls.some(([, options]) => options?.method === 'POST' && JSON.parse(String(options.body)).description === 'Payment services')).toBe(true);
  expect(await screen.findByRole('button', { name: 'Create portfolio' })).toBeInTheDocument();
  expect(await screen.findByRole('link', { name: 'Payments New' })).toBeInTheDocument();
});

it('shows linked applications, permits editing, and displays deletion conflicts', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'DELETE') return json({ detail: 'Cannot delete a portfolio containing applications' }, 409);
    if (options?.method === 'PUT') return json({ ...portfolio, owner: 'Taylor' });
    if (String(url).includes('/applications?')) return json({ items: [{ id: 'a1', name: 'Checkout', lifecycleStatus: 'Active', qualityScore: 80 }], total: 1, offset: 0, limit: 25 });
    return json(portfolio);
  });
  render(<MemoryRouter initialEntries={['/portfolios/p1']}><Routes><Route path="/portfolios/:id" element={<PortfolioDetail user={admin} />} /></Routes></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Checkout' })).toHaveAttribute('href', '/applications/a1');
  const actor = userEvent.setup();
  await actor.click(screen.getByRole('button', { name: 'Edit portfolio' }));
  await actor.clear(screen.getByLabelText('Owner'));
  await actor.type(screen.getByLabelText('Owner'), 'Taylor');
  await actor.click(screen.getByRole('button', { name: 'Save portfolio' }));
  expect(await screen.findByText('Taylor')).toBeInTheDocument();
  await actor.click(screen.getByRole('button', { name: 'Delete portfolio' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Cannot delete a portfolio containing applications');
});

it('does not show mutation controls for a read-only user and reports loading errors', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Permission denied' }, 403));
  render(<MemoryRouter><Portfolios user={{ ...admin, role: 'Read Only' }} /></MemoryRouter>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
  expect(screen.queryByRole('button', { name: 'Create portfolio' })).not.toBeInTheDocument();
});
