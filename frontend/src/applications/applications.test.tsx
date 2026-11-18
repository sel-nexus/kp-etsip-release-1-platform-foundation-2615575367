import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Applications from './Applications';
import ApplicationDetail from './ApplicationDetail';
import type { User } from '../types';

const admin: User = { id: 'u', name: 'Admin', email: 'admin@example.com', role: 'Administrator', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: false };
const app = { id: 'a', name: 'Checkout', portfolioId: 'p', portfolioName: 'Payments', description: 'Demo', productArea: '', businessOwner: 'Owner', technologyOwner: '', etsOwner: '', criticality: 'High', tier: 1, lifecycleStatus: 'Active', technologyStack: '', repositoryLink: null, pipelineLink: null, applicationHealthScore: 80, qualityScore: 90, automationCoverage: 60, unitTestCoverage: 70, openDefects: 2, openCriticalDefects: 1, riskLevel: 'High', createdAt: '', updatedAt: '' };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('renders records and sends filters while hiding read-only actions', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async url => String(url).includes('/portfolios') ? json({ items: [{ id: 'p', name: 'Payments' }] }) : json({ items: [app], total: 1, offset: 0, limit: 25 }));
  render(<MemoryRouter><Applications user={{ ...admin, role: 'Read Only' }} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Checkout' })).toHaveAttribute('href', '/applications/a');
  expect(screen.queryByText('Export CSV')).not.toBeInTheDocument();
  await userEvent.setup().selectOptions(screen.getByLabelText('Criticality'), 'High');
  expect(fetcher.mock.calls.some(([url]) => String(url).includes('criticality=High'))).toBe(true);
});

it('edits all application fields and displays errors', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, opts) => {
    if (opts?.method === 'PUT') return json({ detail: 'Duplicate name' }, 409);
    return String(url).includes('/portfolios') ? json({ items: [{ id: 'p', name: 'Payments' }] }) : json(app);
  });
  render(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:id" element={<ApplicationDetail user={admin} />} /></Routes></MemoryRouter>);
  expect(await screen.findByText('Owner')).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Edit application' }));
  expect(screen.getByLabelText('Unit-test coverage %')).toHaveValue(70);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Save application' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Duplicate name');
});
