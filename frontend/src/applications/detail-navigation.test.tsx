import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import ApplicationDetail from './ApplicationDetail';
import type { User } from '../types';

const admin: User = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'Administrator', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: false };
const first = { id: 'a', name: 'Checkout', portfolioId: 'p', portfolioName: 'Payments', description: 'First record', productArea: '', businessOwner: 'Owner', technologyOwner: '', etsOwner: '', criticality: 'High', tier: 1, lifecycleStatus: 'Active', technologyStack: '', repositoryLink: null, pipelineLink: null, applicationHealthScore: 80, qualityScore: 90, automationCoverage: 60, unitTestCoverage: 70, openDefects: 2, openCriticalDefects: 1, riskLevel: 'High', createdAt: '', updatedAt: '' };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('clears the old edit form while loading a different record that fails', async () => {
  let failSecond!: (response: Response) => void;
  const secondResponse = new Promise<Response>(resolve => { failSecond = resolve; });
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'PUT') return json(first);
    if (String(url).includes('/portfolios')) return json({ items: [{ id: 'p', name: 'Payments' }] });
    if (String(url).endsWith('/applications/a')) return json(first);
    return secondResponse;
  });
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}>
    <Link to="/applications/b">Go to second</Link>
    <Routes><Route path="/applications/:id" element={<ApplicationDetail user={admin} />} /></Routes>
  </MemoryRouter>);

  expect(await screen.findByRole('heading', { name: 'Checkout' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Edit application' }));
  await user.clear(screen.getByLabelText('Name *'));
  await user.type(screen.getByLabelText('Name *'), 'Unsaved first record');
  await user.click(screen.getByRole('link', { name: 'Go to second' }));
  expect(screen.getByRole('status')).toHaveTextContent('Loading application');
  expect(screen.queryByDisplayValue('Unsaved first record')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save application' })).not.toBeInTheDocument();

  await act(async () => { failSecond(json({ detail: 'Application not found' }, 404)); });
  expect(await screen.findByRole('alert')).toHaveTextContent('Application not found');
  expect(screen.queryByText('Checkout')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Edit application' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save application' })).not.toBeInTheDocument();
  expect(fetcher.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(false);
});

it('does not let an earlier save replace the newly loaded record', async () => {
  let finishSave!: (response: Response) => void;
  const saveResponse = new Promise<Response>(resolve => { finishSave = resolve; });
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'PUT') return saveResponse;
    if (String(url).includes('/portfolios')) return json({ items: [{ id: 'p', name: 'Payments' }] });
    if (String(url).endsWith('/applications/a')) return json(first);
    return json({ ...first, id: 'b', name: 'Billing', description: 'Second record' });
  });
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}>
    <Link to="/applications/b">Go to second</Link>
    <Routes><Route path="/applications/:id" element={<ApplicationDetail user={admin} />} /></Routes>
  </MemoryRouter>);

  expect(await screen.findByRole('heading', { name: 'Checkout' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Edit application' }));
  await user.click(screen.getByRole('button', { name: 'Save application' }));
  expect(fetcher.mock.calls.some(([url, options]) => String(url).endsWith('/applications/a') && options?.method === 'PUT')).toBe(true);
  await user.click(screen.getByRole('link', { name: 'Go to second' }));
  expect(await screen.findByRole('heading', { name: 'Billing' })).toBeInTheDocument();
  await act(async () => { finishSave(json(first)); });
  expect(screen.getByRole('heading', { name: 'Billing' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Edit application' }));
  expect(screen.getByLabelText('Name *')).toHaveValue('Billing');
});

it('keeps the newer detail open when an earlier delete completes', async () => {
  let finishDelete!: (response: Response) => void;
  const deleteResponse = new Promise<Response>(resolve => { finishDelete = resolve; });
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'DELETE') return deleteResponse;
    if (String(url).includes('/portfolios')) return json({ items: [{ id: 'p', name: 'Payments' }] });
    if (String(url).endsWith('/applications/a')) return json(first);
    return json({ ...first, id: 'b', name: 'Billing', description: 'Second record' });
  });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}>
    <Link to="/applications/b">Go to second</Link>
    <Routes>
      <Route path="/applications" element={<h1>Application list</h1>} />
      <Route path="/applications/:id" element={<ApplicationDetail user={admin} />} />
    </Routes>
  </MemoryRouter>);

  expect(await screen.findByRole('heading', { name: 'Checkout' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Delete application' }));
  expect(fetcher.mock.calls.some(([url, options]) => String(url).endsWith('/applications/a') && options?.method === 'DELETE')).toBe(true);
  await user.click(screen.getByRole('link', { name: 'Go to second' }));
  expect(await screen.findByRole('heading', { name: 'Billing' })).toBeInTheDocument();
  await act(async () => { finishDelete(new Response(null, { status: 204 })); });
  expect(screen.getByRole('heading', { name: 'Billing' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Application list' })).not.toBeInTheDocument();
});

it('returns to the list when deleting the current record succeeds', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'DELETE') return new Response(null, { status: 204 });
    if (String(url).includes('/portfolios')) return json({ items: [{ id: 'p', name: 'Payments' }] });
    return json(first);
  });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}>
    <Routes>
      <Route path="/applications" element={<h1>Application list</h1>} />
      <Route path="/applications/:id" element={<ApplicationDetail user={admin} />} />
    </Routes>
  </MemoryRouter>);

  expect(await screen.findByRole('heading', { name: 'Checkout' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Delete application' }));
  expect(await screen.findByRole('heading', { name: 'Application list' })).toBeInTheDocument();
});

it('shows a delete failure on the current detail', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    if (options?.method === 'DELETE') return json({ detail: 'Delete failed' }, 500);
    if (String(url).includes('/portfolios')) return json({ items: [{ id: 'p', name: 'Payments' }] });
    return json(first);
  });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}>
    <Routes><Route path="/applications/:id" element={<ApplicationDetail user={admin} />} /></Routes>
  </MemoryRouter>);

  expect(await screen.findByRole('heading', { name: 'Checkout' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Delete application' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Delete failed');
  expect(screen.getByRole('heading', { name: 'Checkout' })).toBeInTheDocument();
});

it('ignores a late response for a previous route after the new record loads', async () => {
  let resolveFirst!: (response: Response) => void;
  const firstResponse = new Promise<Response>(resolve => { resolveFirst = resolve; });
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
    if (String(url).includes('/portfolios')) return json({ items: [{ id: 'p', name: 'Payments' }] });
    if (String(url).endsWith('/applications/a')) return firstResponse;
    return json({ ...first, id: 'b', name: 'Billing', description: 'Second record' });
  });
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/applications/a']}>
    <Link to="/applications/b">Go to second</Link>
    <Routes><Route path="/applications/:id" element={<ApplicationDetail user={admin} />} /></Routes>
  </MemoryRouter>);

  await user.click(screen.getByRole('link', { name: 'Go to second' }));
  expect(await screen.findByRole('heading', { name: 'Billing' })).toBeInTheDocument();
  await act(async () => { resolveFirst(json(first)); });
  expect(screen.getByRole('heading', { name: 'Billing' })).toBeInTheDocument();
  expect(screen.queryByText('Checkout')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Edit application' }));
  expect(screen.getByLabelText('Name *')).toHaveValue('Billing');
});
