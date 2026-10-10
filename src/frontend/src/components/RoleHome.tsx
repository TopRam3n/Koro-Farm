'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Loader2 } from 'lucide-react';
import { MyWork } from '@/components/MyWork';
import { useIdentity } from '@/hooks/useIdentity';

export function RoleHome() {
  const identity = useIdentity();
  const router = useRouter();
  const role = identity.data?.active_role;

  useEffect(() => {
    if (role === 'FARMER') router.replace('/farmer');
    if (role === 'BUYER') router.replace('/marketplace');
  }, [role, router]);

  if (identity.isLoading) return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground"><span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Loading your workspace…</span></div>;
  if (identity.error) return <div role="alert" className="grid min-h-screen place-items-center px-6 text-center"><div><h1 className="text-xl font-semibold">Workspace access unavailable</h1><p className="mt-2 max-w-md text-sm text-muted-foreground">Your account needs an active organization membership. If you have an invitation token, accept it to activate your access.</p><Link href="/signup" className="mt-4 inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground">Accept invitation</Link></div></div>;
  if (role === 'FARMER' || role === 'BUYER') return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground">Opening your workspace…</div>;
  return <MyWork />;
}
