import type { KoroFarmDomainEvent } from '@/domain/events';
import type { ShortfallReport } from './types';

export function createRecoveryEvents(report: ShortfallReport, occurredAt = '2026-08-31T14:00:00-05:00'): KoroFarmDomainEvent[] {
    const base = { occurredAt, requirementId: 'REQ-HOTEL-001', recoveryEpisodeId: 'REC-001', source: 'DEMO' as const };
    const committedKg = 500 - report.lostKg;
    return [
        { ...base, id: 'EVT-001', type: 'allocation.shortfall_reported', actorType: 'FARMER', actorId: 'F-008', allocationId: 'A-008', payload: { lostKg: report.lostKg, remainingKg: report.expectedKg, reason: report.reason } },
        { ...base, id: 'EVT-002', type: 'allocation.lost', actorType: 'SYSTEM', allocationId: 'A-008', payload: { lostKg: report.lostKg } },
        { ...base, id: 'EVT-003', type: 'requirement.at_risk', actorType: 'SYSTEM', payload: { committedKg, requiredKg: 500, shortfallKg: report.lostKg } },
        { ...base, id: 'EVT-004', type: 'allocation.standby_activated', actorType: 'SYSTEM', allocationId: 'A-009', payload: { activatedKg: report.lostKg, farmerId: 'F-009', lotId: 'LOT-STC-06' } },
        { ...base, id: 'EVT-005', type: 'requirement.coverage_restored', actorType: 'SYSTEM', payload: { committedKg: 500, requiredKg: 500 } },
        { ...base, id: 'EVT-006', type: 'recovery.cost_changed', actorType: 'SYSTEM', payload: { previousCostJmd: 186800, recoveredCostJmd: 191400, deltaJmd: 4600 } },
    ];
}

export function projectCoverage(events: KoroFarmDomainEvent[]) {
    const atRisk = events.find(event => event.type === 'requirement.at_risk');
    const restored = events.find(event => event.type === 'requirement.coverage_restored');
    return { initialKg: 500, disruptedKg: atRisk?.type === 'requirement.at_risk' ? atRisk.payload.committedKg : 500, restoredKg: restored?.type === 'requirement.coverage_restored' ? restored.payload.committedKg : undefined };
}
