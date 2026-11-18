import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { request } from '../api';
import type { Application, ApplicationFields, Page, User } from '../types';

const empty: ApplicationFields = { name: '', description: '', portfolioId: '', productArea: '', businessOwner: '', technologyOwner: '', etsOwner: '', criticality: 'Medium', tier: 1, lifecycleStatus: 'Active', technologyStack: '', repositoryLink: null, pipelineLink: null, applicationHealthScore: 0, qualityScore: 0, automationCoverage: 0, unitTestCoverage: 0, openDefects: 0, openCriticalDefects: 0, riskLevel: 'Low' };
const labels: Record<keyof ApplicationFields, string> = { name: 'Name', description: 'Description', portfolioId: 'Portfolio', productArea: 'Product area', businessOwner: 'Business owner', technologyOwner: 'Technology owner', etsOwner: 'ETS owner', criticality: 'Criticality', tier: 'Tier', lifecycleStatus: 'Lifecycle status', technologyStack: 'Technology stack', repositoryLink: 'Repository link', pipelineLink: 'Pipeline link', applicationHealthScore: 'Application health score', qualityScore: 'Quality score', automationCoverage: 'Automation coverage %', unitTestCoverage: 'Unit-test coverage %', openDefects: 'Open defects', openCriticalDefects: 'Open critical defects', riskLevel: 'Risk level' };
const options: Partial<Record<keyof ApplicationFields, string[]>> = { criticality: ['Low', 'Medium', 'High', 'Critical'], lifecycleStatus: ['Active', 'Deprecated', 'Retired'], riskLevel: ['Low', 'Medium', 'High'] };

/** Display and maintain all application attributes. */
export default function ApplicationDetail({ user, creating = false }: { user: User; creating?: boolean }) {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState<Application | null>(null);
  const [value, setValue] = useState<ApplicationFields>(empty);
  const [portfolios, setPortfolios] = useState<{ id: string; name: string }[]>([]);
  const [editing, setEditing] = useState(creating);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([request<Page<{ id: string; name: string }>>('/portfolios?limit=100'), creating ? Promise.resolve(null) : request<Application>(`/applications/${id}`)])
      .then(([p, app]) => { if (active) { setPortfolios(p.items); if (app) { setItem(app); const fields = Object.keys(empty) as (keyof ApplicationFields)[]; setValue(Object.fromEntries(fields.map(key => [key, app[key]])) as unknown as ApplicationFields); } } })
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, creating]);
  const canEdit = ['Administrator', 'Engineer'].includes(user.role) || (user.role === 'Portfolio Leader' && (creating || user.portfolioAccess.includes(item?.portfolioId || '')));
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); setError(''); setSaving(true);
    try {
      const result = await request<Application>(creating ? '/applications' : `/applications/${id}`, { method: creating ? 'POST' : 'PUT', body: JSON.stringify(value) });
      if (creating) navigate(`/applications/${result.id}`); else { setItem(result); setEditing(false); }
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save application.'); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    if (!window.confirm('Delete this application? This cannot be undone.')) return;
    try { await request<void>(`/applications/${id}`, { method: 'DELETE' }); navigate('/applications'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to delete application.'); }
  };
  return (
    <main id="main" className="content">
      <p><Link to="/applications">← All applications</Link></p>
      {loading && <p role="status">Loading application…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && (item || creating) && <>
        <div className="portfolio-heading"><h1>{creating ? 'Create application' : item?.name}</h1><div className="portfolio-actions">{!editing && canEdit && <button onClick={() => setEditing(true)}>Edit application</button>}{!creating && user.role === 'Administrator' && <button className="secondary" onClick={remove}>Delete application</button>}</div></div>
        {editing && canEdit ? <form className="card portfolio-form" onSubmit={save}>
          {(Object.keys(empty) as (keyof ApplicationFields)[]).map(key => {
            const val = value[key];
            const update = (raw: string) => setValue(current => ({ ...current, [key]: typeof val === 'number' ? Number(raw) : (key === 'repositoryLink' || key === 'pipelineLink') ? raw || null : raw }));
            return <div key={key}><label htmlFor={`app-${key}`}>{labels[key]}{key === 'name' || key === 'portfolioId' ? ' *' : ''}</label>
              {key === 'portfolioId' ? <select id={`app-${key}`} required value={String(val || '')} onChange={e => update(e.target.value)}><option value="">Select a portfolio</option>{portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select> : options[key] ? <select id={`app-${key}`} value={String(val)} onChange={e => update(e.target.value)}>{options[key]?.map(v => <option key={v}>{v}</option>)}</select> : <input id={`app-${key}`} required={key === 'name' || typeof val === 'number'} type={typeof val === 'number' ? 'number' : key.endsWith('Link') ? 'url' : 'text'} min={typeof val === 'number' ? (key === 'tier' ? 1 : 0) : undefined} max={key === 'tier' ? 4 : ['applicationHealthScore', 'qualityScore', 'automationCoverage', 'unitTestCoverage'].includes(key) ? 100 : undefined} value={val ?? ''} onChange={e => update(e.target.value)} />}
            </div>;
          })}
          <div className="portfolio-actions"><button disabled={saving}>{saving ? 'Saving…' : 'Save application'}</button><button type="button" className="secondary" onClick={() => creating ? navigate('/applications') : setEditing(false)}>Cancel</button></div>
        </form> : item && <dl>{(Object.keys(empty) as (keyof ApplicationFields)[]).map(key => <div key={key}><dt>{labels[key]}</dt><dd>{key === 'portfolioId' ? item.portfolioName : (key === 'repositoryLink' || key === 'pipelineLink') && item[key] ? <a href={item[key] ?? undefined} target="_blank" rel="noreferrer">{item[key]}</a> : String(item[key] ?? '—')}</dd></div>)}</dl>}
      </>}
    </main>
  );
}
