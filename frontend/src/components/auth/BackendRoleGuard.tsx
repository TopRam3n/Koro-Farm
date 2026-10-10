'use client';
import type { BackendCapability } from '@/features/identity/backendAuthorization'; import { backendCan } from '@/features/identity/backendAuthorization'; import { useMe } from '@/hooks/api/useBackend';
export function BackendRoleGuard({ capability, children }: { capability: BackendCapability; children: React.ReactNode }) { const me = useMe(); return me.data && backendCan(me.data.role, capability) ? <>{children}</> : null; }
