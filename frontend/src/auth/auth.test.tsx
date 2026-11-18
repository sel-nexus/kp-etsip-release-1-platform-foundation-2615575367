import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Login from './Login';
import Profile from './Profile';
import type { User } from '../types';

afterEach(() => { cleanup(); vi.restoreAllMocks(); sessionStorage.clear(); });
const user: User = { id: '1', name: 'Demo Administrator', email: 'admin@ketsip.local', role: 'Administrator', portfolioAccess: [], status: 'Active', defaultLandingPage: null, mustChangePassword: true };

describe('identity screens', () => {
  it('shows a rejected login and never invokes the success handler', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Invalid email or password' }), { status: 401 }));
    const onLogin = vi.fn();
    render(<Login onLogin={onLogin} />);
    const actor = userEvent.setup();
    await actor.type(screen.getByLabelText('Email address'), 'admin@ketsip.local');
    await actor.type(screen.getByLabelText('Password'), 'wrong');
    await actor.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
    expect(onLogin).not.toHaveBeenCalled();
  });

  it('stores a successful login and displays required password change', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ token: 'signed', user }), { status: 200 }));
    const onLogin = vi.fn();
    render(<Login onLogin={onLogin} />);
    const actor = userEvent.setup();
    await actor.type(screen.getByLabelText('Email address'), user.email);
    await actor.type(screen.getByLabelText('Password'), 'DemoPassword123!');
    await actor.click(screen.getByRole('button', { name: 'Sign in' }));
    await screen.findByRole('button', { name: 'Sign in' });
    expect(onLogin).toHaveBeenCalledWith(user);
    expect(sessionStorage.getItem('ketsip.token')).toBe('signed');
    cleanup();
    render(<Profile user={user} onUpdate={vi.fn()} onPasswordChanged={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('change your initial password');
    expect(screen.queryByLabelText('Default landing page')).not.toBeInTheDocument();
  });

  it('saves a landing preference and reports password errors', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch');
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ ...user, mustChangePassword: false, defaultLandingPage: 'applications' }), { status: 200 }));
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Current password is incorrect' }), { status: 400 }));
    const onUpdate = vi.fn();
    render(<Profile user={{ ...user, mustChangePassword: false }} onUpdate={onUpdate} onPasswordChanged={vi.fn()} />);
    const actor = userEvent.setup();
    await actor.selectOptions(screen.getByLabelText('Default landing page'), 'applications');
    await actor.click(screen.getByRole('button', { name: 'Save preference' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Landing preference saved');
    expect(onUpdate).toHaveBeenCalled();
    await actor.type(screen.getByLabelText('Current password'), 'bad');
    await actor.type(screen.getByLabelText('New password'), 'NewPassword123!');
    await actor.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Current password is incorrect');
  });
});
