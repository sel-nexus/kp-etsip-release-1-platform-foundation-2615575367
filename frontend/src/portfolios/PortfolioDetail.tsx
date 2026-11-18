import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { request } from '../api';
import type { User } from '../types';
import { PortfolioForm } from './Portfolios';
import type { Page, Portfolio } from './Portfolios';

interface Application { id: string; name: string; lifecycleStatus: string | null; qualityScore: number | null }

/** Show portfolio details and its linked applications. */
export default function PortfolioDetail({ user }: { user: User }) {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [applications, setApplications] = useState<Page<Application> | null>(null);
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    Promise.all([request<Portfolio>(`/portfolios/${id}`), request<Page<Application>>(`/portfolios/${id}/applications?offset=${offset}`)])
      .then(([p, a]) => { if (active) { setPortfolio(p); setApplications(a); } })
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, offset, revision]);
  const canEdit = user.role === 'Administrator' || (user.role === 'Portfolio Leader' && user.portfolioAccess.includes(id));
  const remove = async () => {
    if (!window.confirm('Delete this portfolio? This cannot be undone.')) return;
    try { await request<void>(`/portfolios/${id}`, { method: 'DELETE' }); navigate('/portfolios'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to delete portfolio.'); }
  };
  return (
    <main id="main" className="content">
      <p><Link to="/portfolios">← All portfolios</Link></p>
      {loading && <p role="status">Loading portfolio…</p>}
      {error && <p className="error" role="alert">{error} <button className="secondary" onClick={() => setRevision(v => v + 1)}>Retry</button></p>}
      {portfolio && !loading && <>
        <div className="portfolio-heading"><div><p className="eyebrow">PORTFOLIO</p><h1>{portfolio.name}</h1><p>{portfolio.description || 'No description provided.'}</p></div><div className="portfolio-actions">{canEdit && !editing && <button onClick={() => setEditing(true)}>Edit portfolio</button>}{user.role === 'Administrator' && <button className="secondary" onClick={remove}>Delete portfolio</button>}</div></div>
        {editing && <PortfolioForm initial={{ name: portfolio.name, owner: portfolio.owner, productArea: portfolio.productArea, description: portfolio.description, status: portfolio.status }} onCancel={() => setEditing(false)} onSave={async value => { const updated = await request<Portfolio>(`/portfolios/${id}`, { method: 'PUT', body: JSON.stringify(value) }); setPortfolio(updated); setEditing(false); }} />}
        <dl><div><dt>Owner</dt><dd>{portfolio.owner || '—'}</dd></div><div><dt>Product area</dt><dd>{portfolio.productArea || '—'}</dd></div><div><dt>Status</dt><dd>{portfolio.status}</dd></div><div><dt>Applications</dt><dd>{portfolio.applicationCount}</dd></div><div><dt>Quality score</dt><dd>{portfolio.qualityScore ?? '—'}</dd></div></dl>
        <h2>Applications</h2>
        {applications && (applications.items.length ? <div className="portfolio-table-wrap"><table className="portfolio-table"><thead><tr><th scope="col">Name</th><th scope="col">Lifecycle status</th><th scope="col">Quality score</th></tr></thead><tbody>{applications.items.map(app => <tr key={app.id}><td><Link to={`/applications/${app.id}`}>{app.name}</Link></td><td>{app.lifecycleStatus || '—'}</td><td>{app.qualityScore ?? '—'}</td></tr>)}</tbody></table></div> : <p>No applications are linked to this portfolio.</p>)}
        {applications && applications.total > applications.limit && <div className="portfolio-pagination"><button className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - applications.limit))}>Previous</button><span>{offset + 1}–{Math.min(offset + applications.items.length, applications.total)} of {applications.total}</span><button className="secondary" disabled={offset + applications.limit >= applications.total} onClick={() => setOffset(offset + applications.limit)}>Next</button></div>}
      </>}
    </main>
  );
}
