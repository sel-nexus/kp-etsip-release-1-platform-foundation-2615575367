import { useState, type FormEvent } from 'react';
import { api, setToken } from '../api';
import type { User } from '../types';

interface Props { onLogin: (user: User) => void }

/** Authenticate with the local identity service. */
export default function Login({ onLogin }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await api.login(email, password);
      setToken(result.token);
      onLogin(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-layout" id="main">
      <section className="intro" aria-labelledby="intro-title">
        <p className="eyebrow">KP ETSIP / PLATFORM FOUNDATION</p>
        <h1 id="intro-title">Clarity for enterprise quality.</h1>
        <p>A shared foundation for understanding your application portfolio, quality and risk.</p>
        <div className="intro-rule" />
        <p className="small">Secure local access · Release 1</p>
      </section>
      <section className="login-panel" aria-labelledby="login-title">
        <p className="eyebrow">WELCOME BACK</p>
        <h2 id="login-title">Sign in</h2>
        <p className="muted">Enter your local account credentials to continue.</p>
        <form onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="username" required aria-required="true" value={email} onChange={e => setEmail(e.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required aria-required="true" value={password} onChange={e => setPassword(e.target.value)} aria-invalid={!!error} aria-describedby={error ? 'login-error' : undefined} />
          {error && <p id="login-error" role="alert" className="error">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <p className="small muted">Demo accounts and initial credentials are documented by your administrator.</p>
      </section>
    </main>
  );
}
