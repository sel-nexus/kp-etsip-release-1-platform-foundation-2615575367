import { useState, type FormEvent } from 'react';
import { api } from '../api';
import type { User } from '../types';

interface Props { user: User; onUpdate: (user: User) => void; onPasswordChanged: () => void }

/** Show account access, landing preference, and password controls. */
export default function Profile({ user, onUpdate, onPasswordChanged }: Props) {
  const [landing, setLanding] = useState<'dashboard' | 'applications'>(user.defaultLandingPage || (['Administrator', 'Executive'].includes(user.role) ? 'dashboard' : 'applications'));
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function saveProfile(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try { onUpdate(await api.profile(landing)); setMessage('Landing preference saved.'); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to save profile.'); }
    finally { setBusy(false); }
  }
  async function savePassword(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try { await api.password(current, next); onPasswordChanged(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to change password.'); }
    finally { setBusy(false); }
  }

  return (
    <main className="content" id="main">
      <p className="eyebrow">ACCOUNT / MY PROFILE</p>
      <h1>My Profile</h1>
      <p className="muted">Manage your account and preferred starting point.</p>
      {user.mustChangePassword && <p className="notice" role="status">For your security, change your initial password before continuing.</p>}
      {error && <p className="error" role="alert" id="profile-error">{error}</p>}
      {message && <p role="status">{message}</p>}
      <div className="profile-grid">
        <section className="card" aria-labelledby="identity-title">
          <h2 id="identity-title">Identity & access</h2>
          <dl>
            <div><dt>Name</dt><dd>{user.name}</dd></div>
            <div><dt>Email</dt><dd>{user.email}</dd></div>
            <div><dt>Role</dt><dd>{user.role}</dd></div>
            <div><dt>Portfolio access</dt><dd>{user.portfolioAccess.length ? user.portfolioAccess.join(', ') : user.role === 'Portfolio Leader' ? 'No assigned portfolios' : 'All portfolios'}</dd></div>
          </dl>
          {!user.mustChangePassword && (
            <form onSubmit={saveProfile}>
              <label htmlFor="landing">Default landing page</label>
              <select id="landing" value={landing} onChange={e => setLanding(e.target.value as 'dashboard' | 'applications')}>
                <option value="dashboard">Executive Dashboard</option>
                <option value="applications">Application Repository</option>
              </select>
              <button type="submit" className="secondary" disabled={busy}>Save preference</button>
            </form>
          )}
        </section>
        <section className="card" aria-labelledby="security-title">
          <h2 id="security-title">Change password</h2>
          <p className="muted">Use at least 12 characters. You will sign in again after changing it.</p>
          <form onSubmit={savePassword}>
            <label htmlFor="current-password">Current password</label>
            <input id="current-password" type="password" autoComplete="current-password" required aria-required="true" value={current} onChange={e => setCurrent(e.target.value)} aria-describedby={error ? 'profile-error' : undefined} />
            <label htmlFor="new-password">New password</label>
            <input id="new-password" type="password" autoComplete="new-password" required aria-required="true" minLength={12} maxLength={72} value={next} onChange={e => setNext(e.target.value)} aria-describedby={error ? 'profile-error' : undefined} />
            <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button>
          </form>
        </section>
      </div>
    </main>
  );
}
