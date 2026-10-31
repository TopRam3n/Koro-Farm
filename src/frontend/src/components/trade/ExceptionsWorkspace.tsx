'use client';

import { ExceptionList } from '@/components/trade/ExceptionList';
import { RecoveryTasks } from '@/components/trade/RecoveryTasks';
import { TradePage } from '@/components/trade/TradeUi';

export function ExceptionsWorkspace() {
  return <TradePage eyebrow="Operations" title="Needs attention"
    description="Supply exceptions raised by deterministic checks, and the recovery agent's proposals for them. The agent only proposes: nothing is activated or sent to a supplier until a person approves the exact proposal."
    crumbs={[{ label: 'Needs attention' }]}>
    <section className="operational-panel p-5" aria-labelledby="recovery-heading">
      <h2 id="recovery-heading" className="text-base font-semibold">Recovery</h2>
      <RecoveryTasks showOrder empty="No recovery in progress." />
    </section>
    <section className="operational-panel mt-6 p-5" aria-labelledby="exceptions-heading">
      <h2 id="exceptions-heading" className="text-base font-semibold">Open exceptions</h2>
      <ExceptionList showOrder empty="No open supply exceptions." />
    </section>
  </TradePage>;
}
