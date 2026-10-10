import type { RoleCode } from '@/domain/types';
export type BackendCapability = 'requirements.write' | 'supply.manage' | 'recovery.execute' | 'recovery.approve' | 'warehouse.write' | 'shipments.write' | 'admin.users' | 'audit.read';
const permissions: Record<RoleCode, readonly BackendCapability[]> = {
    PLATFORM_ADMIN: ['requirements.write', 'supply.manage', 'recovery.execute', 'recovery.approve', 'warehouse.write', 'shipments.write', 'admin.users', 'audit.read'],
    ORGANIZATION_ADMIN: ['recovery.approve', 'admin.users', 'audit.read'], PROCUREMENT_MANAGER: ['requirements.write', 'recovery.approve', 'audit.read'], SUPPLY_COORDINATOR: ['supply.manage', 'recovery.execute', 'audit.read'], WAREHOUSE_OPERATOR: ['warehouse.write', 'shipments.write', 'audit.read'], AUDITOR: ['audit.read'], FARMER: [],
};
export function backendCan(role: RoleCode | null | undefined, capability: BackendCapability) { return role ? permissions[role].includes(capability) : false; }
