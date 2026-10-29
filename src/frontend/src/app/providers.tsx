'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';
import { useState } from 'react';
import { Toaster } from '@/components/ui/toaster';
import { Toaster as Sonner } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuthProvider } from '@/hooks/useAuth';
import { ThemeProvider } from 'next-themes';

export function Providers({ children }: { children: React.ReactNode }) {
  // A 4xx answer (not found, forbidden, invalid) will not change on retry; show it at once. Retry transient failures only.
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: (failures, error) => !(error instanceof ApiError && error.status < 500) && failures < 3 } },
  }));

  return <QueryClientProvider client={queryClient}><ThemeProvider attribute="class" defaultTheme="dark" forcedTheme="dark"><TooltipProvider><AuthProvider>{children}<Toaster /><Sonner /></AuthProvider></TooltipProvider></ThemeProvider></QueryClientProvider>;
}
