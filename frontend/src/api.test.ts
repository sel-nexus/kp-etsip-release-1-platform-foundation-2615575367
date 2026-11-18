import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, downloadCsv, getToken, request, setToken } from './api';

beforeEach(() => sessionStorage.clear());
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

describe('API client session and errors', () => {
  it('stores and removes the token and sends it as a bearer header', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ name: 'Inventory' }));
    setToken('abc');
    expect(getToken()).toBe('abc');
    await expect(request('/items')).resolves.toEqual({ name: 'Inventory' });
    expect(fetcher).toHaveBeenCalledWith('/api/items', expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer abc', 'Content-Type': 'application/json' }) }));
    setToken(null);
    expect(getToken()).toBeNull();
  });

  it('clears a rejected session and emits expiry, but not for a failed login', async () => {
    const expired = vi.fn();
    window.addEventListener('session-expired', expired);
    try {
      const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Bad credentials' }, 401));
      setToken('abc');
      await expect(api.login('x@example.com', 'wrong')).rejects.toThrow('Bad credentials');
      expect(getToken()).toBe('abc');
      expect(expired).not.toHaveBeenCalled();
      fetcher.mockResolvedValueOnce(json({ detail: 'Expired' }, 401));
      await expect(api.me()).rejects.toThrow('Expired');
      expect(getToken()).toBeNull();
      expect(expired).toHaveBeenCalledOnce();
    } finally { window.removeEventListener('session-expired', expired); }
  });

  it('handles empty success, invalid error bodies and network failure', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response('not json', { status: 500 }))
      .mockRejectedValueOnce(new TypeError('Network unavailable'));
    await expect(request('/empty')).resolves.toBeUndefined();
    await expect(request('/broken')).rejects.toThrow('Unable to complete request.');
    await expect(request('/offline')).rejects.toThrow('Network unavailable');
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('downloads authenticated CSV and revokes its temporary URL', async () => {
    setToken('abc');
    const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('name\nCheckout', { status: 200 }));
    const create = vi.fn(() => 'blob:test');
    const revoke = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('inventory.csv');
      expect(this.href).toBe('blob:test');
    });
    await downloadCsv('/applications/export', 'inventory.csv');
    expect(fetcher).toHaveBeenCalledWith('/api/applications/export', { headers: { Authorization: 'Bearer abc' } });
    expect(click).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith('blob:test');
  });

  it('expires the session on a rejected CSV and reports fallback errors', async () => {
    const expired = vi.fn();
    window.addEventListener('session-expired', expired);
    try {
      setToken('abc');
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('bad', { status: 401 }));
      await expect(downloadCsv('/applications/export')).rejects.toThrow('Unable to export CSV.');
      expect(getToken()).toBeNull();
      expect(expired).toHaveBeenCalledOnce();
    } finally { window.removeEventListener('session-expired', expired); }
  });
});
