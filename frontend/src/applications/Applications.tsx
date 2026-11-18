import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { downloadCsv, request } from '../api';
import type { Application, Page, User } from '../types';

/** Browse the scoped application inventory. */
export default function Applications({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState<Page<Application> | null>(null);
  const [portfolios, setPortfolios] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const query = params.toString();
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    request<Page<Application>>(`/applications${query ? `?${query}` : ''}`)
      .then(result => { if (active) setPage(result); })
      .catch(e => { if (active) { setPage(null); setError(e.message); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, revision]);
  useEffect(() => {
    let active = true;
    request<Page<{ id: string; name: string }>>('/portfolios?limit=100')
      .then(result => { if (active) setPortfolios(result.items); })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'offset') next.delete('offset');
    setParams(next);
  };
  const exportCsv = async () => {
    const filters = new URLSearchParams(params); filters.delete('offset'); filters.delete('limit');
    try { await downloadCsv(`/applications/export?${filters}`); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to export applications.'); }
  };
  return (
    <main id="main" className="content">
      <div className="portfolio-heading">
        <div><p className="eyebrow">INVENTORY</p><h1>Application Repository</h1><p className="muted">Explore application quality and risk.</p></div>
        <div className="portfolio-actions">
          {['Administrator', 'Engineer', 'Portfolio Leader'].includes(user.role) && <Link to="/applications/new">Create application</Link>}
          {user.role !== 'Read Only' && <button className="secondary" onClick={exportCsv}>Export CSV</button>}
        </div>
      </div>
      <div className="portfolio-filters">
        <label>Search<input value={params.get('search') || ''} onChange={e => change('search', e.target.value)} /></label>
        <label>Portfolio<select value={params.get('portfolioId') || ''} onChange={e => change('portfolioId', e.target.value)}><option value="">All portfolios</option>{portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        {([['criticality', 'Criticality', ['Low', 'Medium', 'High', 'Critical']], ['riskLevel', 'Risk level', ['Low', 'Medium', 'High']], ['lifecycleStatus', 'Lifecycle status', ['Active', 'Deprecated', 'Retired']]] as const).map(([key, label, options]) => <label key={key}>{label}<select value={params.get(key) || ''} onChange={e => change(key, e.target.value)}><option value="">All</option>{options.map(value => <option key={value}>{value}</option>)}</select></label>)}
      </div>
      {loading && <p role="status">Loading applications…</p>}
      {error && <p className="error" role="alert">{error} <button className="secondary" onClick={() => setRevision(v => v + 1)}>Retry</button></p>}
      {!loading && page && <>
        {page.items.length === 0 ? <p>No applications match these filters.</p> : <div className="portfolio-table-wrap"><table className="portfolio-table"><thead><tr>{['Name', 'Portfolio', 'Criticality', 'Tier', 'Lifecycle Status', 'Health Score', 'Automation Coverage %', 'Open Critical Defects', 'Risk Level'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>
          {page.items.map(item => <tr key={item.id}><td><Link to={`/applications/${item.id}`}>{item.name}</Link></td><td>{item.portfolioName}</td><td>{item.criticality}</td><td>{item.tier}</td><td>{item.lifecycleStatus}</td><td>{item.applicationHealthScore}</td><td>{item.automationCoverage}%</td><td>{item.openCriticalDefects}</td><td>{item.riskLevel}</td></tr>)}
        </tbody></table></div>}
        <div className="portfolio-pagination"><button className="secondary" disabled={page.offset === 0} onClick={() => change('offset', String(Math.max(0, page.offset - page.limit)))}>Previous</button><span>Showing {page.total ? page.offset + 1 : 0}–{Math.min(page.offset + page.items.length, page.total)} of {page.total}</span><button className="secondary" disabled={page.offset + page.limit >= page.total} onClick={() => change('offset', String(page.offset + page.limit))}>Next</button></div>
      </>}
    </main>
  );
}
