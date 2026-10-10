import { supabase } from '@/integrations/supabase/client';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) return {};
  const organizationId = typeof window !== 'undefined' ? window.localStorage.getItem('korofarm:active-organization-id') : null;
  return {
    Authorization: `Bearer ${token}`,
    ...(organizationId ? { 'X-Organization-ID': organizationId } : {}),
  };
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  method: string,
  path: string,
  options: {
    body?: unknown;
    params?: Record<string, string | number | boolean | undefined | null>;
    idempotencyKey?: string;
  } = {},
): Promise<T> {
  const authHeaders = await getAuthHeaders();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...authHeaders,
  };

  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey;
  }

  let url = `${BACKEND_URL}${path}`;
  if (options.params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(options.params)) {
      if (value !== undefined && value !== null) {
        searchParams.set(key, String(value));
      }
    }
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (cause) {
    throw new ApiError(0, cause, `Unable to reach KoroFarm backend at ${BACKEND_URL}`);
  }

  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = await res.text(); }
    throw new ApiError(res.status, body, `API ${method} ${path} → ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined | null>) =>
    request<T>('GET', path, { params }),

  post: <T>(path: string, body?: unknown, idempotencyKey?: string) =>
    request<T>('POST', path, { body, idempotencyKey: idempotencyKey ?? crypto.randomUUID() }),

  patch: <T>(path: string, body?: unknown, idempotencyKey?: string) =>
    request<T>('PATCH', path, { body, idempotencyKey: idempotencyKey ?? crypto.randomUUID() }),
};

export async function apiBlob(path: string): Promise<Blob> {
  const authHeaders = await getAuthHeaders();
  const res = await fetch(`${BACKEND_URL}${path}`, { headers: authHeaders });
  if (!res.ok) throw new ApiError(res.status, await res.text(), `API GET ${path} → ${res.status}`);
  return res.blob();
}

/** Generate a stable idempotency key for a given intent, stored in session storage so retries reuse it. */
export function getOrCreateIdempotencyKey(intentKey: string): string {
  if (typeof window === 'undefined') return crypto.randomUUID();
  const stored = sessionStorage.getItem(`idem:${intentKey}`);
  if (stored) return stored;
  const key = crypto.randomUUID();
  sessionStorage.setItem(`idem:${intentKey}`, key);
  return key;
}

/** Clear idempotency key after successful mutation (so next distinct action gets a fresh key). */
export function clearIdempotencyKey(intentKey: string): void {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem(`idem:${intentKey}`);
}
