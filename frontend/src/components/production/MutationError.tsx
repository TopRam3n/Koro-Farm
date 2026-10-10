import { ApiError } from '@/lib/api/client';

export function mutationErrorMessage(error: Error | null, fallback = 'The action could not be completed. You can safely retry.'): string | null {
    if (!error) return null;
    if (error instanceof ApiError && error.status === 0) return 'Cannot reach the KoroFarm service. Check your connection and try again.';
    if (error instanceof ApiError && error.status === 409) return 'The record changed while you were working. Refresh the data and try again.';
    if (error instanceof ApiError && error.status === 403) return 'Your role does not permit this action.';
    return fallback;
}

export function MutationError({ error, fallback }: { error: Error | null; fallback?: string }) {
    const message = mutationErrorMessage(error, fallback);
    return message ? <p className="text-sm text-destructive" role="alert">{message}</p> : null;
}
