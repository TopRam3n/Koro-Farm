export interface Escalation {
    id: string; type: 'COORDINATOR_HELP' | 'RECOVERY_FAILED' | 'ORG_APPROVAL' | 'TOKEN_ISSUE' | 'COMPLIANCE_REVIEW';
    relatedEntityId: string; createdAt: string; priority: 'LOW' | 'MEDIUM' | 'HIGH';
    owner?: string; status: 'OPEN' | 'ASSIGNED'; contextHref: string;
}
