'use client';

import { Loader2 } from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { resolvePostLoginRoute } from '@/features/identity/auth/routing';

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, memberships, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user && pathname === '/') router.replace('/login');
    if (!isLoading && user && pathname === '/') router.replace(resolvePostLoginRoute(memberships));
  }, [isLoading, memberships, pathname, router, user]);

  if (isLoading || (!user && pathname === '/')) return <div className="flex min-h-screen items-center justify-center bg-background"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;
  return <>{children}</>;
}
