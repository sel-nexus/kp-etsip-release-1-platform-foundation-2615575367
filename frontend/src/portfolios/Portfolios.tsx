import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { request } from '../api';
import type { User } from '../types';

export interface PortfolioFields { name: string; owner: string; description: string; productArea: string; status: 'Active' | 'Archived' }
export interface Portfolio extends PortfolioFields { id: string; applicationCount: number; qualityScore: number | null; createdAt: string; updatedAt: string }
export interface Page<T> { items: T[]; total: number; offset: number; limit: number }
const empty: PortfolioFields = { name: '', owner: '', description: '', productArea: '', status: 'Active' };

/** Collect all editable portfolio fields and surface server validation errors. */
export function PortfolioForm({ initial = empty, onSave, onCancel }: { initial?: PortfolioFields; onSave: (value: PortfolioFields) => Promise<void>; onCancel: () => void }) {
  const [value, setValue] = useState<PortfolioFields>(initial);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!value.name.trim()) { setError('Name is required.'); return; }
    setSaving(true); setError('');
    try { await onSave(value); } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save portfolio.'); }
    finally { setSaving(false); }
  };
  return (
    <form className="card portfolio-form" onSubmit={submit}>
      <h2>{initial === empty ? 'Create portfolio' : 'Edit portfolio'}</h2>
      {error && <p className="error" role="alert">{error}</p>}
      <label htmlFor="portfolio-name">Name *</label>
      <input id="portfolio-name" required maxLength={200} value={value.name} onChange={e => setValue({ ...value, name: e.target.value })} />
      <label htmlFor="portfolio-owner">Owner</label>
      <input id="portfolio-owner" maxLength={200} value={value.owner} onChange={e => setValue({ ...value, owner: e.target.value })} />
      <label htmlFor="portfolio-area">Product area</label>
      <input id="portfolio-area" maxLength={200} value={value.productArea} onChange={e => setValue({ ...value, productArea: e.target.value })} />
      <label htmlFor="portfolio-description">Description</label>
      <textarea id="portfolio-description" maxLength={5000} value={value.description} onChange={e => setValue({ ...value, description: e.target.value })} />
      <label htmlFor="portfolio-status">Status</label>
      <select id="portfolio-status" value={value.status} onChange={e => setValue({ ...value, status: e.target.value as PortfolioFields['status'] })}>
        <option>Active</option><option>Archived</option>
      </select>
      <div className="portfolio-actions">
        <button disabled={saving} type="submit">{saving ? 'Saving…' : 'Save portfolio'}</button>
        <button className="secondary" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** Browse, filter, and create portfolio records. */
export default function Portfolios({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState<Page<Portfolio> | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revision, setRevision] = useState(0);
  const query = params.toString();
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    request<Page<Portfolio>>(`/portfolios${query ? `?${query}` : ''}`).then(result => { if (active) setPage(result); }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, revision]);
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'offset') next.delete('offset');
    setParams(next);
  };
  return (
    <main id="main" className="content">
      <div className="portfolio-heading">
        <div><p className="eyebrow">INVENTORY</p><h1>Portfolios</h1><p className="muted">Explore portfolio ownership and application quality.</p></div>
        {user.role === 'Administrator' && !creating && <button onClick={() => setCreating(true)}>Create portfolio</button>}
      </div>
      {creating && <PortfolioForm onCancel={() => setCreating(false)} onSave={async value => { await request('/portfolios', { method: 'POST', body: JSON.stringify(value) }); setCreating(false); setRevision(v => v + 1); }} />}
      <div className="portfolio-filters">
        <label>Search<input value={params.get('search') || ''} onChange={e => change('search', e.target.value)} /></label>
        <label>Status<select value={params.get('status') || ''} onChange={e => change('status', e.target.value)}><option value="">All statuses</option><option>Active</option><option>Archived</option></select></label>
        <label>Filter by product area<input value={params.get('productArea') || ''} onChange={e => change('productArea', e.target.value)} /></label>
      </div>
      {loading && <p role="status">Loading portfolios…</p>}
      {error && <p className="error" role="alert">{error} <button className="secondary" onClick={() => setRevision(v => v + 1)}>Retry</button></p>}
      {!loading && !error && page && <>
        <p className="muted">{page.total} {page.total === 1 ? 'portfolio' : 'portfolios'}</p>
        {page.items.length === 0 ? <p>No portfolios match these filters.</p> : <div className="portfolio-table-wrap"><table className="portfolio-table"><thead><tr><th scope="col">Name</th><th scope="col">Owner</th><th scope="col">Product Area</th><th scope="col">Applications</th><th scope="col">Quality Score</th><th scope="col">Status</th></tr></thead><tbody>
          {page.items.map(item => <tr key={item.id}><td><Link to={`/portfolios/${item.id}`}>{item.name}</Link></td><td>{item.owner || '—'}</td><td>{item.productArea || '—'}</td><td>{item.applicationCount}</td><td>{item.qualityScore ?? '—'}</td><td>{item.status}</td></tr>)}
        </tbody></table></div>}
        <div className="portfolio-pagination"><button className="secondary" disabled={page.offset === 0} onClick={() => change('offset', String(Math.max(0, page.offset - page.limit)))}>Previous</button><span>Showing {page.total ? page.offset + 1 : 0}–{Math.min(page.offset + page.items.length, page.total)} of {page.total}</span><button className="secondary" disabled={page.offset + page.limit >= page.total} onClick={() => change('offset', String(page.offset + page.limit))}>Next</button></div>
      </>}
    </main>
  );
}
