import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, Link, useNavigate } from 'react-router-dom';
import { api, getToken, setToken } from './api';
import type { User } from './types';
import Login from './auth/Login';
import Profile from './auth/Profile';

/** Coordinate the persisted session and identity routes. */
function AppRoutes() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!getToken());
  const [notice, setNotice] = useState('');
  const navigate = useNavigate();
  useEffect(() => {
    const expired = () => { setUser(null); setNotice('Your session has expired. Sign in again.'); navigate('/login'); };
    window.addEventListener('session-expired', expired);
    if (getToken()) {
      api.me().then(setUser).catch(() => { setUser(null); setNotice('Unable to restore your session. Sign in again.'); setToken(null); }).finally(() => setLoading(false));
    }
    return () => window.removeEventListener('session-expired', expired);
  }, [navigate]);
  const signOut = async () => {
    try { await api.logout(); } catch { setNotice('Session cleared locally; server sign-out could not be confirmed.'); }
    finally { setToken(null); setUser(null); navigate('/login'); }
  };
  const signedIn = (value: User) => {
    setUser(value); setNotice('');
    navigate(value.mustChangePassword ? '/profile' : `/${value.defaultLandingPage || (['Administrator', 'Executive'].includes(value.role) ? 'dashboard' : 'applications')}`);
  };
  if (loading) return <main className="content" aria-live="polite">Restoring session…</main>;
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="header">
        <Link to="/" className="brand"><span className="brand-mark">K</span><span>KP ETSIP <small>PLATFORM FOUNDATION</small></span></Link>
        {user && <nav aria-label="Account navigation"><Link to="/profile">My Profile</Link><button className="text-button" onClick={signOut}>Sign out</button></nav>}
      </header>
      {notice && <p className="session-notice" role="status">{notice}</p>}
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/profile" replace /> : <Login onLogin={signedIn} />} />
        <Route path="/profile" element={user ? <Profile user={user} onUpdate={setUser} onPasswordChanged={() => { setToken(null); setUser(null); setNotice('Password changed. Please sign in again.'); navigate('/login'); }} /> : <Navigate to="/login" replace />} />
        <Route path="/dashboard" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <main id="main" className="content"><h1>Executive Dashboard</h1><p>This area is not yet available in the identity release.</p><Link to="/profile">Manage your profile</Link></main> : <Navigate to="/login" replace />} />
        <Route path="/applications" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <main id="main" className="content"><h1>Application Repository</h1><p>This area is not yet available in the identity release.</p><Link to="/profile">Manage your profile</Link></main> : <Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to={user ? user.mustChangePassword ? '/profile' : `/${user.defaultLandingPage || (['Administrator', 'Executive'].includes(user.role) ? 'dashboard' : 'applications')}` : '/login'} replace />} />
      </Routes>
    </>
  );
}

/** Install the single client-side router. */
export default function App() { return <BrowserRouter><AppRoutes /></BrowserRouter>; }
