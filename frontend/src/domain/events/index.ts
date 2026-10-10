export type ActorType = 'BUYER' | 'FARMER' | 'OPS' | 'SYSTEM';

export interface DomainEvent<TType extends string = string, TPayload = unknown> {
    id: string;
    type: TType;
    occurredAt: string;
    actorType: ActorType;
    actorId?: string;
    requirementId?: string;
    requestId?: string;
    allocationId?: string;
    recoveryEpisodeId?: string;
    payload: TPayload;
    source: 'LIVE' | 'DEMO';
}

export interface ShortfallReportedPayload { lostKg: number; remainingKg: number; reason: string; }
export interface AllocationLostPayload { lostKg: number; }
export interface RequirementAtRiskPayload { committedKg: number; requiredKg: number; shortfallKg: number; }
export interface StandbyActivatedPayload { activatedKg: number; farmerId: string; lotId?: string; }
export interface CoverageRestoredPayload { committedKg: number; requiredKg: number; }
export interface RecoveryCostChangedPayload { previousCostJmd: number; recoveredCostJmd: number; deltaJmd: number; }

export type KoroFarmDomainEvent =
    | DomainEvent<'allocation.shortfall_reported', ShortfallReportedPayload>
    | DomainEvent<'allocation.lost', AllocationLostPayload>
    | DomainEvent<'requirement.at_risk', RequirementAtRiskPayload>
    | DomainEvent<'allocation.standby_activated', StandbyActivatedPayload>
    | DomainEvent<'requirement.coverage_restored', CoverageRestoredPayload>
    | DomainEvent<'recovery.cost_changed', RecoveryCostChangedPayload>;
