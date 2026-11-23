'use client';

import { use } from 'react';
import { AuthGate } from '@/components/AuthGate';
import { OrderDetail } from '@/components/trade/OrderDetail';

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <AuthGate><OrderDetail id={id} /></AuthGate>;
}
