'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';
import { useState } from 'react';
import { Toaster } from '@/components/ui/toaster';
import { Toaster as Sonner } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuthProvider } from '@/hooks/useAuth';
import { ThemeProvider } from 'next-themes';

// The offline demo replay was retired (29 Oct 2026): it modelled a pre-R1 flow without supplier consent and could be
// mistaken for live behaviour. A build configured for it shows this notice instead of any application screen.
const DEMO_REPLAY_REQUESTED = process.env.NEXT_PUBLIC_APP_MODE === 'demo';

function DemoReplayDisabled() {
  return <main className="grid min-h-screen place-items-center bg-background px-6 text-foreground">
    <div role="alert" className="max-w-lg rounded-[10px] border border-white/[0.08] bg-card p-8">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">Configuration</p>
      <h1 className="mt-3 text-2xl font-semibold">The offline demo replay is disabled</h1>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">It showed an earlier workflow that no longer matches how KoroFarm records supplier agreement. Remove <code>NEXT_PUBLIC_APP_MODE=demo</code> and connect the live API with a signed-in account.</p>
    </div>
  </main>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return DEMO_REPLAY_REQUESTED ? <DemoReplayDisabled /> : <LiveProviders>{children}</LiveProviders>;
}

function LiveProviders({ children }: { children: React.ReactNode }) {
  // A 4xx answer (not found, forbidden, invalid) will not change on retry; show it at once. Retry transient failures only.
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: (failures, error) => !(error instanceof ApiError && error.status < 500) && failures < 3 } },
  }));

  return <QueryClientProvider client={queryClient}><ThemeProvider attribute="class" defaultTheme="dark" forcedTheme="dark"><TooltipProvider><AuthProvider>{children}<Toaster /><Sonner /></AuthProvider></TooltipProvider></ThemeProvider></QueryClientProvider>;
}
