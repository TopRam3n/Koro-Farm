import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: vi.fn(async () => ({ data: { session: null } })) } },
}));

import { apiFetch } from '@/lib/api';

describe('API boundary failures', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('surfaces backend error detail without fabricating data', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'controlled failure' }), { status: 500 })));
    await expect(apiFetch('/failure')).rejects.toThrow('controlled failure');
  });

  it('rejects malformed success JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{partial', { status: 200 })));
    await expect(apiFetch('/malformed')).rejects.toThrow('invalid JSON');
  });

  it('does not automatically switch to offline demo state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network offline'); }));
    await expect(apiFetch('/requirements/id/assurance')).rejects.toThrow('network offline');
  });
});
