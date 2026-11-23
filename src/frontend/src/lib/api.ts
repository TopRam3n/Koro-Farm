import { supabase } from '@/integrations/supabase/client';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const ORGANIZATION_KEY = 'korofarm.organizationId';

/** An API failure that keeps the HTTP status, so callers can tell a conflict (409) from a validation error (422). */
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly detail: unknown = null) {
    super(message);
    this.name = 'ApiError';
  }
}

/** The organization the signed-in user is working in (chosen from their memberships). */
export function selectedOrganizationId(): string | null {
  try { return window.localStorage.getItem(ORGANIZATION_KEY); } catch { return null; }
}

export function selectOrganization(id: string | null) {
  try {
    if (id) window.localStorage.setItem(ORGANIZATION_KEY, id);
    else window.localStorage.removeItem(ORGANIZATION_KEY);
  } catch { /* storage unavailable: the API falls back to the user's single membership */ }
}

function describe(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{ loc: [...], msg }]
    return detail.map((item: { loc?: unknown[]; msg?: string }) => {
      const field = Array.isArray(item.loc) ? item.loc.filter(part => part !== 'body').join('.') : '';
      return field ? `${field}: ${item.msg}` : item.msg;
    }).join('; ');
  }
  return `API request failed: ${status}`;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const organizationId = selectedOrganizationId() ?? process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? null;
  const controller = options.signal ? null : new AbortController();
  const timeout = controller ? setTimeout(() => controller.abort(), 10_000) : null;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(organizationId ? { 'X-Organization-ID': organizationId } : {}),
        ...options.headers,
      },
      signal: options.signal ?? controller?.signal,
    });
  } finally {
    if (timeout) clearTimeout(timeout);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(describe(body?.detail, response.status), response.status, body?.detail ?? null);
  }

  try {
    return await response.json();
  } catch {
    throw new ApiError('API returned an invalid JSON response', response.status);
  }
}
