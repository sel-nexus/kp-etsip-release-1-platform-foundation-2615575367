import type { LoginResponse, User } from './types';

const base = import.meta.env.VITE_API_BASE || '/api';
const tokenKey = 'ketsip.token';

/** Read the current browser session token. */
export const getToken = (): string | null => sessionStorage.getItem(tokenKey);
/** Store or erase the current browser session token. */
export function setToken(token: string | null): void {
  if (token) sessionStorage.setItem(tokenKey, token);
  else sessionStorage.removeItem(tokenKey);
}

/** Request JSON and clear invalid sessions outside the login exchange. */
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') {
      setToken(null);
      window.dispatchEvent(new Event('session-expired'));
    }
    const body: { detail?: unknown } = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to complete request.');
  }
  return response.json() as Promise<T>;
}

/** Provide typed calls for the identity API. */
export const api = {
  login: (email: string, password: string) => request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<User>('/auth/me'),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),
  profile: (defaultLandingPage: User['defaultLandingPage']) => request<User>('/auth/profile', { method: 'PUT', body: JSON.stringify({ defaultLandingPage }) }),
  password: (currentPassword: string, newPassword: string) => request<{ status: string }>('/auth/password', { method: 'POST', body: JSON.stringify({ currentPassword, newPassword }) }),
};
