'use client';

import { use, useEffect } from 'react';
import { AuthGate } from '@/components/AuthGate';
import { rememberActiveOrder } from '@/hooks/useActiveRequirement';
import Index from '@/pages/Index';

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  useEffect(() => { rememberActiveOrder(id); }, [id]);
  return <AuthGate><Index requirementId={id} /></AuthGate>;
}
