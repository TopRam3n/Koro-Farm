import type { FarmerRequest, FarmerRequestDecision } from './types';

export function isRequestExpired(request: FarmerRequest, now: Date = new Date()) {
    return request.state === 'EXPIRED' || new Date(request.responseExpiresAt).getTime() <= now.getTime();
}

export function selectActionableRequests(requests: FarmerRequest[], now: Date = new Date()) {
    return requests.filter(request => ['PENDING', 'VIEWED'].includes(request.state) && !isRequestExpired(request, now)).sort((a, b) => Date.parse(a.responseExpiresAt) - Date.parse(b.responseExpiresAt));
}

export function decideRequest(request: FarmerRequest, acceptedKg: number, now: Date = new Date()): FarmerRequestDecision {
    if (isRequestExpired(request, now)) throw new Error('REQUEST_EXPIRED');
    if (!Number.isFinite(acceptedKg) || acceptedKg <= 0 || acceptedKg > request.requestedKg) throw new Error('INVALID_ACCEPTED_QUANTITY');
    return { type: 'ACCEPT', acceptedKg, remainderKg: request.requestedKg - acceptedKg };
}
