import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import Reports from './Reports';
import type { User } from '../types';

const user: User = { id: 'u', name: 'Reader', email: 'u@example.com', role: 'Read Only', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: false };
const portfolio = { id: 'p', name: 'Payments', owner: 'Owner', productArea: 'Commerce', status: 'Active', applicationCount: 2, qualityScore: 81, applicationsAtRisk: 1 };
const metrics = { enterpriseQualityScore: 81, applicationHealthScore: 62, automationMaturityScore: 71, openCriticalDefects: 5, applicationsAtRisk: 1, totalApplications: 2, totalPortfolios: 1, portfolios: [portfolio] };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('shows metrics and updates them for selected filters', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async url => String(url).includes('/dashboard') ? json(String(url).includes('riskLevel=High') ? { ...metrics, totalApplications: 1 } : metrics) : json({ items: [portfolio], total: 1 }));
  render(<MemoryRouter><Dashboard /></MemoryRouter>);
  expect(await screen.findByText('Enterprise Quality Score')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Payments' })).toHaveAttribute('href', '/portfolios/p');
  await userEvent.setup().selectOptions(screen.getByLabelText('Risk level'), 'High');
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes('riskLevel=High'))).toBe(true));
  await waitFor(() => expect(screen.getByText('Total Applications').parentElement).toHaveTextContent('1'));
});

it('shows empty averages and empty portfolio breakdowns', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => String(url).includes('/dashboard') ? json({ ...metrics, enterpriseQualityScore: null, portfolios: [] }) : json({ items: [], total: 0 }));
  render(<MemoryRouter><Dashboard /></MemoryRouter>);
  expect(await screen.findByText('—')).toBeInTheDocument();
  expect(screen.getAllByText('No portfolios match these filters.')).toHaveLength(2);
});

it('switches report tables, applies filters and hides export for read-only users', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
    if (String(url).includes('/reports/portfolios')) return json({ items: String(url).includes('riskLevel=High') ? [] : [portfolio], total: String(url).includes('riskLevel=High') ? 0 : 1, offset: 0, limit: 25 });
    if (String(url).includes('/reports/applications')) return json({ items: [], total: 0, offset: 0, limit: 25 });
    return json({ items: [portfolio], total: 1 });
  });
  render(<MemoryRouter><Reports user={user} /></MemoryRouter>);
  expect(await screen.findByText('No records match these filters.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
  await userEvent.setup().selectOptions(screen.getByLabelText('Report'), 'portfolios');
  expect(await screen.findByRole('link', { name: 'Payments' })).toBeInTheDocument();
  await userEvent.setup().selectOptions(screen.getByLabelText('Risk level'), 'High');
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes('/reports/portfolios?') && String(url).includes('riskLevel=High'))).toBe(true));
  expect(await screen.findByText('No records match these filters.')).toBeInTheDocument();
});

it('shows a denied export to an otherwise export-capable role', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => String(url).includes('format=csv') ? json({ detail: 'Permission denied' }, 403) : json({ items: [], total: 0, offset: 0, limit: 25 }));
  render(<MemoryRouter><Reports user={{ ...user, role: 'Executive' }} /></MemoryRouter>);
  await screen.findByText('No records match these filters.');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Export CSV' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
});
