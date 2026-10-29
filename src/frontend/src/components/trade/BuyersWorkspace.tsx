'use client';

import { useState } from 'react';
import { useBuyers, useCreateBuyer } from '@/hooks/useTrade';
import { ErrorNote, Field, LoadState, SubmitButton, TextArea, TradePage, formValues } from '@/components/trade/TradeUi';
import { HonestEmpty } from '@/components/WorkspacePrimitives';

export function BuyersWorkspace() {
  const buyers = useBuyers();
  const create = useCreateBuyer();
  const [created, setCreated] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setCreated(null);
    const buyer = await create.mutateAsync(formValues(form)).catch(() => null);
    if (buyer) { form.reset(); setCreated(buyer.name); }
  }

  return <TradePage eyebrow="Demand" title="Buyers" description="Institutional buyers your organization supplies. Orders are placed for a buyer."
    crumbs={[{ label: 'Orders', href: '/orders' }, { label: 'Buyers' }]}>
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <section aria-labelledby="buyers-list" className="operational-panel p-5">
        <h2 id="buyers-list" className="text-base font-semibold">Your buyers</h2>
        <LoadState query={buyers} empty={<HonestEmpty title="No buyers yet" detail="Add the first buyer you supply." />}>
          <ul className="mt-3 divide-y divide-white/[0.07]" aria-label="Buyers">
            {buyers.data?.map(buyer => <li key={buyer.id} className="py-3">
              <p className="font-medium">{buyer.name}</p>
              <p className="text-xs text-muted-foreground">{buyer.buyer_type} · delivers to {buyer.destination}</p>
            </li>)}
          </ul>
        </LoadState>
      </section>
      <section aria-labelledby="new-buyer" className="operational-panel p-5">
        <h2 id="new-buyer" className="text-base font-semibold">Add a buyer</h2>
        <form className="mt-3 space-y-3" onSubmit={onSubmit}>
          <Field label="Buyer name" name="name" required minLength={2} />
          <Field label="Buyer type" name="buyer_type" required placeholder="e.g. Hotel, Processor, School" />
          <Field label="Delivery destination" name="destination" required />
          <TextArea label="Notes" name="notes" />
          <SubmitButton busy={create.isPending}>Add buyer</SubmitButton>
          <ErrorNote error={create.error} />
          {created && <p role="status" className="text-sm text-success">Saved {created}.</p>}
        </form>
      </section>
    </div>
  </TradePage>;
}
