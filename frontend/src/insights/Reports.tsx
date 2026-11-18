import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { downloadCsv, request } from '../api';
import type { Application, InsightPortfolio, Page, User } from '../types';
import { InsightFilters } from './Dashboard';

/** Browse and export filtered application and portfolio reports. */
export default function Reports({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const kind = params.get('report') === 'portfolios' ? 'portfolios' : 'applications';
  const [page, setPage] = useState<Page<Application | InsightPortfolio> | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const query = params.toString();
  useEffect(() => {
    let active = true;
    const filters = new URLSearchParams(query); filters.delete('report');
    setLoading(true); setError(''); setPage(null);
    request<Page<Application | InsightPortfolio>>(`/reports/${kind}?${filters}`).then(value => { if (active) setPage(value); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Unable to load report.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, kind]);
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    if (key !== 'offset') next.delete('offset');
    setParams(next);
  };
  const exportReport = async () => {
    const filters = new URLSearchParams(params); filters.delete('report'); filters.delete('offset'); filters.delete('limit'); filters.set('format', 'csv');
    try { await downloadCsv(`/reports/${kind}?${filters}`, `${kind}.csv`); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to export report.'); }
  };
  return <main id="main" className="content">
    <div className="portfolio-heading">
      <div><p className="eyebrow">INSIGHTS</p><h1>Reports</h1><p className="muted">View and export visible inventory.</p></div>
      {user.role !== 'Read Only' && <button className="secondary" onClick={exportReport}>Export CSV</button>}
    </div>
    <label>Report
      <select value={kind} onChange={e => change('report', e.target.value)}>
        <option value="applications">Application Report</option>
        <option value="portfolios">Portfolio Report</option>
      </select>
    </label>
    <InsightFilters />
    {loading && <p role="status">Loading report…</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {page && <>
      {page.items.length === 0 ? <p>No records match these filters.</p> : <div className="portfolio-table-wrap"><table className="portfolio-table">
        <thead><tr>{(kind === 'applications' ? ['Name', 'Portfolio', 'Product Area', 'Criticality', 'Tier', 'Lifecycle', 'Health', 'Quality', 'Automation %', 'Unit Test %', 'Open Defects', 'Critical Defects', 'Risk'] : ['Name', 'Owner', 'Product Area', 'Applications', 'Quality Score', 'Status']).map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{page.items.map(row => kind === 'applications' ? (() => { const a = row as Application; return <tr key={a.id}>
          <td><Link to={`/applications/${a.id}`}>{a.name}</Link></td><td>{a.portfolioName}</td><td>{a.productArea}</td><td>{a.criticality}</td><td>{a.tier}</td><td>{a.lifecycleStatus}</td><td>{a.applicationHealthScore}</td><td>{a.qualityScore}</td><td>{a.automationCoverage}</td><td>{a.unitTestCoverage}</td><td>{a.openDefects}</td><td>{a.openCriticalDefects}</td><td>{a.riskLevel}</td>
        </tr>; })() : (() => { const p = row as InsightPortfolio; return <tr key={p.id}>
          <td><Link to={`/portfolios/${p.id}`}>{p.name}</Link></td><td>{p.owner}</td><td>{p.productArea}</td><td>{p.applicationCount}</td><td>{p.qualityScore ?? '—'}</td><td>{p.status}</td>
        </tr>; })())}</tbody>
      </table></div>}
      <div className="portfolio-pagination">
        <button className="secondary" disabled={page.offset === 0} onClick={() => change('offset', String(Math.max(0, page.offset - page.limit)))}>Previous</button>
        <span>Showing {page.total ? page.offset + 1 : 0}–{Math.min(page.offset + page.items.length, page.total)} of {page.total}</span>
        <button className="secondary" disabled={page.offset + page.limit >= page.total} onClick={() => change('offset', String(page.offset + page.limit))}>Next</button>
      </div>
    </>}
  </main>;
}
