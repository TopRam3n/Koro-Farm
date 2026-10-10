export interface FulfilmentEvidence { requiredKg: number; receivedKg: number; acceptedKg: number; rejectedKg: number; }
export function validateFulfilment(e: FulfilmentEvidence) { if (e.receivedKg < 0 || e.acceptedKg < 0 || e.rejectedKg < 0) return false; if (e.acceptedKg + e.rejectedKg > e.receivedKg) return false; return true }
export function pendingGradingKg(e: FulfilmentEvidence) { if (!validateFulfilment(e)) throw new Error('INVALID_FULFILMENT_EVIDENCE'); return e.receivedKg - e.acceptedKg - e.rejectedKg }
