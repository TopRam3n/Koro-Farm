'use client';

import { ExceptionList } from '@/components/trade/ExceptionList';
import { TradePage } from '@/components/trade/TradeUi';

export function ExceptionsWorkspace() {
  return <TradePage eyebrow="Operations" title="Needs attention"
    description="Supply exceptions raised by deterministic checks: commitments no longer covered by reported capacity, supplier replies past their deadline, and expired standby that affects recovery. Nothing here is acted on automatically."
    crumbs={[{ label: 'Needs attention' }]}>
    <section className="operational-panel p-5" aria-label="Open exceptions">
      <ExceptionList showOrder empty="No open supply exceptions." />
    </section>
  </TradePage>;
}
