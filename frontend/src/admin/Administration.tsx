import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { downloadCsv, request } from '../api';
import type { AdminRole, AdminUser, AuditEvent, Page, User } from '../types';
import type { Portfolio } from '../portfolios/Portfolios';

const ceilings: Record<string, string[]> = {
  Administrator: ['view', 'create', 'edit', 'delete', 'export', 'administer'],
  Executive: ['view', 'export'], 'Portfolio Leader': ['view', 'create', 'edit', 'export'],
  Engineer: ['view', 'create', 'edit', 'export'], Auditor: ['view', 'export'], 'Read Only': ['view'],
};
const allPermissions = ['view', 'create', 'edit', 'delete', 'export', 'administer'];
interface UserFields { name: string; email: string; role: string; portfolioAccess: string[]; status: string; managerName: string | null; vendorIndicator: boolean; password?: string }
const emptyUser: UserFields = { name: '', email: '', role: 'Engineer', portfolioAccess: [], status: 'Active', managerName: null, vendorIndicator: false, password: '' };

/** Administer users and policies or inspect the audit trail. */
export default function Administration({ user }: { user: User }) {
  const admin = user.role === 'Administrator';
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab');
  const tab = admin && (requested === 'users' || requested === 'roles') ? requested : 'audit';
  const [users, setUsers] = useState<Page<AdminUser> | null>(null);
  const [roles, setRoles] = useState<AdminRole[] | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [audit, setAudit] = useState<Page<AuditEvent> | null>(null);
  const [editing, setEditing] = useState<UserFields | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [roleEdit, setRoleEdit] = useState<AdminRole | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const query = new URLSearchParams();
  for (const key of ['userId', 'action']) if (params.get(key)) query.set(key, params.get(key)!);
  for (const key of ['from', 'to']) {
    const value = params.get(key);
    if (value) query.set(key, new Date(`${value}T${key === 'from' ? '00:00:00' : '23:59:59'}`).toISOString());
  }
  query.set('offset', params.get('offset') || '0');
  const auditQuery = query.toString();
  const search = params.get('search') || '';
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    if (tab === 'audit') setAudit(null);
    else if (tab === 'users') setUsers(null);
    else { setRoles(null); setRoleEdit(null); }
    const load = async () => {
      if (tab === 'audit') {
        const result = await request<Page<AuditEvent>>(`/audit-logs?${auditQuery}`);
        if (active) setAudit(result);
      } else if (tab === 'roles') {
        const result = await request<Page<AdminRole>>('/roles?limit=100');
        if (active) setRoles(result.items);
      } else {
        const accounts = await request<Page<AdminUser>>(`/users?search=${encodeURIComponent(search)}&offset=${params.get('offset') || '0'}`);
        const all: Portfolio[] = [];
        let offset = 0;
        let total = 0;
        do {
          const scope = await request<Page<Portfolio>>(`/portfolios?limit=100&offset=${offset}`);
          all.push(...scope.items);
          total = scope.total;
          offset += scope.items.length;
          if (!scope.items.length) break;
        } while (offset < total);
        if (active) { setUsers(accounts); setPortfolios(all); }
      }
    };
    load().catch(e => { if (active) setError(e instanceof Error ? e.message : 'Unable to load administration.'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [tab, auditQuery, search, revision]);
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'offset') next.delete('offset');
    setParams(next);
  };
  const perform = async (operation: () => Promise<void>, message: string) => {
    setBusy(true); setError(''); setNotice('');
    try { await operation(); setNotice(message); setRevision(v => v + 1); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to complete request.'); }
    finally { setBusy(false); }
  };
  const page = tab === 'users' ? users : audit;
  return (
    <main id="main" className="content">
      <p className="eyebrow">ACCESS AND GOVERNANCE</p>
      <h1>Administration</h1>
      <p className="muted">Manage access and review sensitive activity.</p>
      <nav className="admin-tabs" aria-label="Administration sections">
        {admin && <button className={tab === 'users' ? '' : 'secondary'} aria-current={tab === 'users' ? 'page' : undefined} onClick={() => change('tab', 'users')}>Users</button>}
        {admin && <button className={tab === 'roles' ? '' : 'secondary'} aria-current={tab === 'roles' ? 'page' : undefined} onClick={() => change('tab', 'roles')}>Roles</button>}
        <button className={tab === 'audit' ? '' : 'secondary'} aria-current={tab === 'audit' ? 'page' : undefined} onClick={() => change('tab', 'audit')}>Audit log</button>
      </nav>
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {loading && <p role="status">Loading…</p>}
      {tab === 'users' && admin && <section>
        <div className="portfolio-heading">
          <h2>Users</h2>
          <button onClick={() => { setEditing({ ...emptyUser }); setEditingId(null); }}>Create user</button>
        </div>
        <label>Search users<input value={search} onChange={e => change('search', e.target.value)} /></label>
        {editing && <form className="card portfolio-form" onSubmit={e => { e.preventDefault(); void perform(async () => {
          await request(editingId ? `/users/${editingId}` : '/users', { method: editingId ? 'PUT' : 'POST', body: JSON.stringify(editing) }); setEditing(null);
        }, 'User saved.'); }}>
          <h2>{editingId ? 'Edit user' : 'Create user'}</h2>
          <label htmlFor="admin-name">Name</label>
          <input id="admin-name" required maxLength={200} value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} />
          <label htmlFor="admin-email">Email</label>
          <input id="admin-email" type="email" required value={editing.email} onChange={e => setEditing({ ...editing, email: e.target.value })} />
          {!editingId && <>
            <label htmlFor="admin-password">Initial password</label>
            <input id="admin-password" type="password" required minLength={12} maxLength={72} value={editing.password || ''} onChange={e => setEditing({ ...editing, password: e.target.value })} />
          </>}
          <label htmlFor="admin-role">Role</label>
          <select id="admin-role" value={editing.role} onChange={e => setEditing({ ...editing, role: e.target.value })}>{Object.keys(ceilings).map(role => <option key={role}>{role}</option>)}</select>
          <label htmlFor="admin-status">Status</label>
          <select id="admin-status" value={editing.status} onChange={e => setEditing({ ...editing, status: e.target.value })}>
            <option>Active</option>
            <option>Inactive</option>
          </select>
          <label htmlFor="admin-manager">Manager name</label>
          <input id="admin-manager" value={editing.managerName || ''} onChange={e => setEditing({ ...editing, managerName: e.target.value || null })} />
          <label className="admin-check"><input type="checkbox" checked={editing.vendorIndicator} onChange={e => setEditing({ ...editing, vendorIndicator: e.target.checked })} /> Vendor</label>
          <fieldset>
            <legend>Portfolio access</legend>
            <p className="muted small">Empty scope gives Portfolio Leaders no access. Other roles follow their role visibility.</p>
            {portfolios.map(portfolio => <label className="admin-check" key={portfolio.id}>
              <input type="checkbox" checked={editing.portfolioAccess.includes(portfolio.id)} onChange={e => setEditing({ ...editing, portfolioAccess: e.target.checked ? [...editing.portfolioAccess, portfolio.id] : editing.portfolioAccess.filter(id => id !== portfolio.id) })} /> {portfolio.name}
            </label>)}
          </fieldset>
          <div className="portfolio-actions">
            <button disabled={busy}>Save user</button>
            <button type="button" className="secondary" onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </form>}
        {!loading && users && <div className="portfolio-table-wrap">
          <table className="portfolio-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.items.map(item => <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.email}</td>
                <td>{item.role}</td>
                <td>{item.status}</td>
                <td>
                  <button className="secondary" onClick={() => { setEditingId(item.id); setEditing({ name: item.name, email: item.email, role: item.role, portfolioAccess: item.portfolioAccess, status: item.status, managerName: item.managerName, vendorIndicator: item.vendorIndicator }); }}>Edit {item.name}</button>
                  {item.status === 'Active' && item.id !== user.id && <button className="secondary" onClick={() => { if (window.confirm(`Deactivate ${item.name}?`)) void perform(async () => { await request(`/users/${item.id}`, { method: 'DELETE' }); }, 'User deactivated.'); }}>Deactivate {item.name}</button>}
                </td>
              </tr>)}
            </tbody>
          </table>
          {!users.items.length && <p>No users found.</p>}
        </div>}
      </section>}
      {tab === 'roles' && admin && <section>
        <h2>Roles</h2>
        {roleEdit && <form className="card portfolio-form" onSubmit={e => { e.preventDefault(); void perform(async () => { await request(`/roles/${roleEdit.id}`, { method: 'PUT', body: JSON.stringify({ name: roleEdit.name, description: roleEdit.description, permissions: roleEdit.permissions }) }); setRoleEdit(null); }, 'Role saved.'); }}>
          <h2>Edit {roleEdit.name}</h2>
          <label htmlFor="role-description">Description</label>
          <input id="role-description" value={roleEdit.description} onChange={e => setRoleEdit({ ...roleEdit, description: e.target.value })} />
          <fieldset>
            <legend>Permissions</legend>
            {allPermissions.map(permission => <label className="admin-check" key={permission}>
              <input type="checkbox" disabled={!ceilings[roleEdit.name].includes(permission)} checked={roleEdit.permissions.includes(permission)} onChange={e => setRoleEdit({ ...roleEdit, permissions: e.target.checked ? [...roleEdit.permissions, permission] : roleEdit.permissions.filter(p => p !== permission) })} /> {permission}
            </label>)}
          </fieldset>
          <div className="portfolio-actions">
            <button disabled={busy}>Save role</button>
            <button type="button" className="secondary" onClick={() => setRoleEdit(null)}>Cancel</button>
          </div>
        </form>}
        {!loading && roles && <div className="portfolio-table-wrap">
          <table className="portfolio-table">
            <thead>
              <tr>
                <th scope="col">Role</th>
                <th scope="col">Permissions</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {roles.map(role => <tr key={role.id}>
                <td>{role.name}</td>
                <td>{role.permissions.join(', ') || 'None'}</td>
                <td>
                  <button className="secondary" onClick={() => setRoleEdit(role)}>Edit {role.name}</button>
                </td>
              </tr>)}
            </tbody>
          </table>
        </div>}
      </section>}
      {tab === 'audit' && <section>
        <div className="portfolio-heading">
          <h2>Audit log</h2>
          <button className="secondary" disabled={busy} onClick={() => void perform(() => downloadCsv(`/audit-logs?${auditQuery}&format=csv`, 'audit-log.csv'), 'Audit page exported.')}>Export CSV</button>
        </div>
        <div className="portfolio-filters">
          <label>User ID<input value={params.get('userId') || ''} onChange={e => change('userId', e.target.value)} /></label>
          <label>Action<select value={params.get('action') || ''} onChange={e => change('action', e.target.value)}>
              <option value="">All actions</option>
              {['login', 'create', 'edit', 'delete', 'roleChange', 'permissionChange', 'export'].map(action => <option key={action}>{action}</option>)}
            </select></label>
          <label>From<input type="date" value={params.get('from') || ''} onChange={e => change('from', e.target.value)} /></label>
          <label>To<input type="date" value={params.get('to') || ''} onChange={e => change('to', e.target.value)} /></label>
        </div>
        {!loading && audit && <div className="portfolio-table-wrap">
          <table className="portfolio-table">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">User</th>
                <th scope="col">Action</th>
                <th scope="col">Entity</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {audit.items.map(event => <tr key={event.id}>
                <td>{new Date(event.timestamp).toLocaleString()}</td>
                <td>{event.userName}</td>
                <td>{event.action}</td>
                <td>{event.entityType}</td>
                <td>{event.details}</td>
              </tr>)}
            </tbody>
          </table>
          {!audit.items.length && <p>No audit events match these filters.</p>}
        </div>}
      </section>}
      {tab !== 'roles' && page && !loading && <div className="portfolio-pagination">
        <button className="secondary" disabled={page.offset === 0} onClick={() => change('offset', String(Math.max(0, page.offset - page.limit)))}>Previous</button>
        <span>Showing {page.total ? page.offset + 1 : 0}–{Math.min(page.offset + page.items.length, page.total)} of {page.total}</span>
        <button className="secondary" disabled={page.offset + page.limit >= page.total} onClick={() => change('offset', String(page.offset + page.limit))}>Next</button>
      </div>}
    </main>
  );
}
