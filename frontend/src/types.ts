/** Public identity returned by the API; password hashes are never sent. */
export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  portfolioAccess: string[];
  status: string;
  defaultLandingPage: 'dashboard' | 'applications' | null;
  mustChangePassword: boolean;
}

/** The login exchange returns a bearer token and public identity. */
export interface LoginResponse { token: string; user: User }
