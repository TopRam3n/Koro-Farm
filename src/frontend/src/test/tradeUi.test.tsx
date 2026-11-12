import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ErrorNote, SupplyStatePill, VerificationPill, formValues } from '@/components/trade/TradeUi';
import { ApiError, apiFetch } from '@/lib/api';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }) } } }));

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); window.localStorage.clear(); });

describe('supply states stay distinct', () => {
  it.each([
    ['PROPOSED', 'NONE', 'Proposed'],
    ['SOLICITED', 'NONE', 'Awaiting supplier'],
    ['COMMITTED', 'RECORDED', 'Committed'],
    ['STANDBY', 'RECORDED', 'Authorized standby'],
    ['COMMITTED', 'UNSUPPORTED_LEGACY', 'Unsupported legacy'],
    ['STANDBY', 'UNSUPPORTED_LEGACY', 'Unsupported legacy'],
  ])('%s with consent %s reads "%s"', (status, consent, label) => {
    render(<SupplyStatePill status={status} consent={consent} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('never labels declared capacity as verified', () => {
    render(<VerificationPill state="DECLARED" />);
    expect(screen.getByText('Declared')).toBeInTheDocument();
    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
  });
});

describe('errors are shown as the server stated them', () => {
  it('presents a 409 as a conflict', () => {
    render(<ErrorNote error={new ApiError('order was changed by someone else', 409)} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Conflict: order was changed by someone else');
  });

  it('turns FastAPI validation details into readable field messages', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'attestation_method'], msg: 'Field required' }] }), { status: 422 })));
    await expect(apiFetch('/allocations/x/responses', { method: 'POST' })).rejects.toMatchObject({ status: 422, message: 'attestation_method: Field required' });
  });

  it('sends the organization the user selected', async () => {
    const fetchMock = vi.fn(async () => new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    window.localStorage.setItem('korofarm.organizationId', 'org-123');
    await apiFetch('/requirements');
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)['X-Organization-ID']).toBe('org-123');
  });
});

describe('form values', () => {
  it('drops blank optional fields instead of sending empty strings', () => {
    document.body.innerHTML = '<form><input name="name" value=" Marcia Ellis "><input name="contact_phone" value=""></form>';
    expect(formValues(document.querySelector('form')!)).toEqual({ name: 'Marcia Ellis' });
  });
});
