'use client';

import { Loader2 } from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const demoMode = process.env.NEXT_PUBLIC_APP_MODE === 'demo' || process.env.NEXT_PUBLIC_AUTH_MODE === 'demo';

  useEffect(() => {
    if (demoMode) return;
    if (!isLoading && !user && pathname === '/') router.replace('/login');
  }, [demoMode, isLoading, pathname, router, user]);

  if (demoMode) return <>{children}</>;

  if (isLoading || (!user && pathname === '/')) return <div className="flex min-h-screen items-center justify-center bg-background"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;
  return <>{children}</>;
}
