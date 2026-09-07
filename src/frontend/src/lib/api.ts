import { supabase } from '@/integrations/supabase/client';
import { demoApiFetch } from '@/lib/demoApi';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (process.env.NEXT_PUBLIC_APP_MODE === 'demo') return demoApiFetch<T>(path, options);
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const controller = options.signal ? null : new AbortController();
  const timeout = controller ? setTimeout(() => controller.abort(), 10_000) : null;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
      signal: options.signal ?? controller?.signal,
    });
  } finally {
    if (timeout) clearTimeout(timeout);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `API request failed: ${response.status}`);
  }

  try {
    return await response.json();
  } catch {
    throw new Error('API returned an invalid JSON response');
  }
}
