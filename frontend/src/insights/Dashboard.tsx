import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { request } from '../api';
import type { ExecutiveMetrics, Page } from '../types';

/** Share URL-backed inventory filters across insight views. */
export function InsightFilters() {
  const [params, setParams] = useSearchParams();
  const [portfolios, setPortfolios] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    async function load() {
      const items: { id: string; name: string }[] = [];
      let offset = 0;
      do {
        const page = await request<Page<{ id: string; name: string }>>(`/portfolios?limit=100&offset=${offset}`);
        items.push(...page.items);
        offset += page.items.length;
        if (offset >= page.total || !page.items.length) break;
      } while (active);
      if (active) setPortfolios(items);
    }
    load().catch(e => { if (active) setError(e instanceof Error ? e.message : 'Unable to load portfolios.'); });
    return () => { active = false; };
  }, []);
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  return <>
    <div className="portfolio-filters">
      <label>Portfolio
        <select value={params.get('portfolioId') || ''} onChange={e => change('portfolioId', e.target.value)}>
          <option value="">All portfolios</option>
          {portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <label>Product area<input value={params.get('productArea') || ''} onChange={e => change('productArea', e.target.value)} /></label>
      <label>Risk level
        <select value={params.get('riskLevel') || ''} onChange={e => change('riskLevel', e.target.value)}>
          <option value="">All risk levels</option>
          {['Low', 'Medium', 'High'].map(value => <option key={value}>{value}</option>)}
        </select>
      </label>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
  </>;
}

/** Present selected application metrics and per-portfolio breakdowns. */
export default function Dashboard() {
  const [params] = useSearchParams();
  const [data, setData] = useState<ExecutiveMetrics | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const query = params.toString();
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setData(null);
    request<ExecutiveMetrics>(`/dashboard/executive?${query}`).then(value => { if (active) setData(value); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Unable to load dashboard.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query]);
  const metrics: [string, number | null][] = data ? [
    ['Enterprise Quality Score', data.enterpriseQualityScore], ['Application Health Score', data.applicationHealthScore],
    ['Automation Maturity Score', data.automationMaturityScore], ['Open Critical Defects', data.openCriticalDefects],
    ['Applications at Risk', data.applicationsAtRisk], ['Total Applications', data.totalApplications], ['Total Portfolios', data.totalPortfolios],
  ] : [];
  return <main id="main" className="content">
    <p className="eyebrow">INSIGHTS</p>
    <h1>Executive Dashboard</h1>
    <p className="muted">Quality and risk from your visible application inventory.</p>
    <InsightFilters />
    {loading && <p role="status">Loading dashboard…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {data && <>
      <section className="insight-metrics" aria-label="Executive metrics">
        {metrics.map(([label, value]) => <div className="card insight-metric" key={label}><span>{label}</span><strong>{value ?? '—'}</strong></div>)}
      </section>
      <section className="insight-breakdown">
        <h2>Portfolio Quality Score</h2>
        {data.portfolios.length === 0 ? <p>No portfolios match these filters.</p> : <ul className="insight-list">
          {data.portfolios.map(p => <li key={p.id}><Link to={`/portfolios/${p.id}`}>{p.name}</Link><span>{p.qualityScore ?? '—'}</span></li>)}
        </ul>}
      </section>
      <section className="insight-breakdown">
        <h2>Applications at Risk by portfolio</h2>
        {data.portfolios.length === 0 ? <p>No portfolios match these filters.</p> : <ul className="insight-list">
          {data.portfolios.map(p => <li key={p.id}><span>{p.name}</span><strong>{p.applicationsAtRisk}</strong></li>)}
        </ul>}
      </section>
    </>}
  </main>;
}
