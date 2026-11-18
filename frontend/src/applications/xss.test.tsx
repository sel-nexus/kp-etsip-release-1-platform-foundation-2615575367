import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Applications from './Applications';
import ApplicationDetail from './ApplicationDetail';
import type { User } from '../types';

const user: User = { id: 'u', name: 'Reader', email: 'r@example.com', role: 'Read Only', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: false };
const payload = '<img src=x onerror="window.__xss=1">';
const app = { id: 'a', name: payload, description: payload, portfolioId: 'p', portfolioName: 'Payments', productArea: '', businessOwner: '', technologyOwner: '', etsOwner: '', criticality: 'Low', tier: 1, lifecycleStatus: 'Active', technologyStack: '', repositoryLink: null, pipelineLink: null, applicationHealthScore: 0, qualityScore: 0, automationCoverage: 0, unitTestCoverage: 0, openDefects: 0, openCriticalDefects: 0, riskLevel: 'Low', createdAt: '', updatedAt: '' };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('renders hostile inventory names literally instead of creating markup', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => String(url).includes('/portfolios') ? json({ items: [] }) : json({ items: [app], total: 1, offset: 0, limit: 25 }));
  const { container } = render(<MemoryRouter><Applications user={user} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: payload })).toHaveTextContent(payload);
  expect(container.querySelector('img')).toBeNull();
});

it('renders hostile detail fields literally and denies edit to read-only users', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => String(url).includes('/portfolios') ? json({ items: [] }) : json(app));
  const { container } = render(<MemoryRouter initialEntries={['/applications/a']}><Routes><Route path="/applications/:id" element={<ApplicationDetail user={user} />} /></Routes></MemoryRouter>);
  expect(await screen.findByRole('heading', { name: payload })).toBeInTheDocument();
  expect(screen.getAllByText(payload)).toHaveLength(3);
  expect(screen.queryByRole('button', { name: 'Edit application' })).not.toBeInTheDocument();
  expect(container.querySelector('img')).toBeNull();
});

it('hides previously loaded inventory when a later filtered query fails and restores it on retry', async () => {
  let failFilteredQuery = true;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async url => {
    if (String(url).includes('/portfolios')) return json({ items: [] });
    if (String(url).includes('riskLevel=High') && failFilteredQuery) return json({ detail: 'Inventory unavailable' }, 503);
    return json({ items: [app], total: 1, offset: 0, limit: 25 });
  });
  const actor = userEvent.setup();
  render(<MemoryRouter><Applications user={user} /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: payload })).toBeInTheDocument();
  await actor.selectOptions(screen.getByLabelText('Risk level'), 'High');
  expect(await screen.findByRole('alert')).toHaveTextContent('Inventory unavailable');
  expect(screen.queryByRole('link', { name: payload })).not.toBeInTheDocument();
  expect(screen.queryByText(/Showing .* of 1/)).not.toBeInTheDocument();
  failFilteredQuery = false;
  await actor.click(screen.getByRole('button', { name: 'Retry' }));
  expect(await screen.findByRole('link', { name: payload })).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
