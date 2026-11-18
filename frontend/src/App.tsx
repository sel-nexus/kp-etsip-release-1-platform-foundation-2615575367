import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, Link, useNavigate } from 'react-router-dom';
import { api, getToken, setToken } from './api';
import type { User } from './types';
import Login from './auth/Login';
import Profile from './auth/Profile';
import Portfolios from './portfolios/Portfolios';
import PortfolioDetail from './portfolios/PortfolioDetail';
import Applications from './applications/Applications';
import ApplicationDetail from './applications/ApplicationDetail';
import Administration from './admin/Administration';
import Dashboard from './insights/Dashboard';
import Reports from './insights/Reports';

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
        {user && <nav aria-label="Account navigation">{!user.mustChangePassword && <><Link to="/dashboard">Dashboard</Link><Link to="/applications">Applications</Link><Link to="/portfolios">Portfolios</Link><Link to="/reports">Reports</Link>{['Administrator', 'Auditor'].includes(user.role) && <Link to="/administration">Administration</Link>}</>}<Link to="/profile">My Profile</Link><button className="text-button" onClick={signOut}>Sign out</button></nav>}
      </header>
      {notice && <p className="session-notice" role="status">{notice}</p>}
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/profile" replace /> : <Login onLogin={signedIn} />} />
        <Route path="/profile" element={user ? <Profile user={user} onUpdate={setUser} onPasswordChanged={() => { setToken(null); setUser(null); setNotice('Password changed. Please sign in again.'); navigate('/login'); }} /> : <Navigate to="/login" replace />} />
        <Route path="/dashboard" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <Dashboard /> : <Navigate to="/login" replace />} />
        <Route path="/reports" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <Reports user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/applications" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <Applications user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/applications/new" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <ApplicationDetail key="new" user={user} creating /> : <Navigate to="/login" replace />} />
        <Route path="/applications/:id" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <ApplicationDetail key="detail" user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/administration" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : ['Administrator', 'Auditor'].includes(user.role) ? <Administration user={user} /> : <main id="main" className="content"><h1>Access denied</h1></main> : <Navigate to="/login" replace />} />
        <Route path="/portfolios" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <Portfolios user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/portfolios/:id" element={user ? user.mustChangePassword ? <Navigate to="/profile" replace /> : <PortfolioDetail user={user} /> : <Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to={user ? user.mustChangePassword ? '/profile' : `/${user.defaultLandingPage || (['Administrator', 'Executive'].includes(user.role) ? 'dashboard' : 'applications')}` : '/login'} replace />} />
      </Routes>
    </>
  );
}

/** Install the single client-side router. */
export default function App() { return <BrowserRouter><AppRoutes /></BrowserRouter>; }
