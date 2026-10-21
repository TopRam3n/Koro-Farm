'use client';

import { Loader2 } from 'lucide-react';
import { useIdentity } from '@/hooks/useIdentity';

export function RoleGate({ allowedRoles, children }: { allowedRoles: readonly string[]; children: React.ReactNode }) {
  const identity = useIdentity();
  if (identity.isLoading) return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground"><span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Checking workspace access…</span></div>;
  if (identity.error) return <div role="alert" className="grid min-h-screen place-items-center px-6 text-center"><div><h1 className="text-xl font-semibold">Workspace access unavailable</h1><p className="mt-2 max-w-md text-sm text-muted-foreground">An active organization membership is required for this workspace.</p></div></div>;
  if (!identity.data || !allowedRoles.includes(identity.data.active_role)) return <div role="alert" className="grid min-h-screen place-items-center px-6 text-center"><div><h1 className="text-xl font-semibold">This workspace is not assigned to your account</h1><p className="mt-2 max-w-md text-sm text-muted-foreground">Contact your organization administrator if you need access.</p></div></div>;
  return children;
}
