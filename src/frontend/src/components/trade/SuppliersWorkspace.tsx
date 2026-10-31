'use client';

import { useState } from 'react';
import { useCreateFarmer, useCreateLot, useCrops, useFarmers, useLots, useRelayCapacity } from '@/hooks/useTrade';
import { ErrorNote, Field, LoadState, Select, SubmitButton, TradePage, VerificationPill, formValues, kg } from '@/components/trade/TradeUi';
import { HonestEmpty } from '@/components/WorkspacePrimitives';

export function SuppliersWorkspace() {
  const farmers = useFarmers();
  const lots = useLots();
  const crops = useCrops();
  const createFarmer = useCreateFarmer();
  const createLot = useCreateLot();
  const relay = useRelayCapacity();
  const [saved, setSaved] = useState<string | null>(null);

  async function onFarmer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setSaved(null);
    const farmer = await createFarmer.mutateAsync(formValues(form)).catch(() => null);
    if (farmer) { form.reset(); setSaved(`Saved supplier ${farmer.name}.`); }
  }

  async function onLot(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setSaved(null);
    const lot = await createLot.mutateAsync(formValues(form)).catch(() => null);
    if (lot) { form.reset(); setSaved(`Recorded ${kg(lot.available_quantity_kg)} of ${lot.crop} for ${lot.farmer_name} as declared.`); }
  }

  async function onCapacity(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setSaved(null);
    const { production_lot_id: lotId, reported_capacity_kg, original_source, attestation_method, evidence_reference } = formValues(form);
    const lot = lots.data?.find(l => l.id === lotId);
    const ok = await relay.mutateAsync({ lotId, reported_capacity_kg, original_source, attestation_method, evidence_reference: evidence_reference ?? null }).then(() => true, () => false);
    if (ok) {
      form.reset();
      setSaved(`Recorded ${lot?.farmer_name ?? 'the supplier'}'s capacity report of ${kg(reported_capacity_kg)}. Orders whose commitments it no longer covers are flagged in Needs attention.`);
    }
  }

  return <TradePage eyebrow="Supply" title="Suppliers and lots" description="Farmers you work with and the production they have declared. Declared figures are not verified capacity."
    crumbs={[{ label: 'Orders', href: '/orders' }, { label: 'Suppliers and lots' }]}>
    {saved && <p role="status" className="mb-4 text-sm text-success">{saved}</p>}
    <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
      <div className="space-y-6">
        <section aria-labelledby="suppliers-list" className="operational-panel p-5">
          <h2 id="suppliers-list" className="text-base font-semibold">Suppliers</h2>
          <LoadState query={farmers} empty={<HonestEmpty title="No suppliers yet" detail="Add a farmer before recording their production." />}>
            <ul className="mt-3 divide-y divide-white/[0.07]" aria-label="Suppliers">
              {farmers.data?.map(farmer => <li key={farmer.id} className="flex flex-wrap items-baseline justify-between gap-2 py-3">
                <span><span className="font-medium">{farmer.name}</span> <span className="text-xs text-muted-foreground">· {farmer.parish}</span></span>
                <span className="text-xs text-muted-foreground">{farmer.production_lot_count ?? 0} lots · {kg(farmer.committed_quantity_kg)} committed</span>
              </li>)}
            </ul>
          </LoadState>
        </section>
        <section aria-labelledby="lots-list" className="operational-panel p-5">
          <h2 id="lots-list" className="text-base font-semibold">Production lots</h2>
          <LoadState query={lots} empty={<HonestEmpty title="No production recorded" detail="Record a farmer's declared lot to make it available for orders." />}>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm" aria-label="Production lots">
                <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-2">Supplier</th><th>Crop</th><th>Harvest</th><th className="text-right">Available</th><th className="text-right">Still to supply</th><th className="text-right">Reserved</th><th className="pl-3">Capacity</th></tr></thead>
                <tbody className="divide-y divide-white/[0.07]">
                  {lots.data?.map(lot => <tr key={lot.id}>
                    <td className="py-2">{lot.farmer_name}</td><td>{lot.crop} · {lot.quality_grade_estimate}</td>
                    <td className="text-xs">{lot.harvest_start} → {lot.harvest_end}</td>
                    <td className="text-right">{kg(lot.available_quantity_kg)}</td>
                    <td className="text-right" title={lot.capacity_reported_at ? `Reported ${new Date(lot.capacity_reported_at).toLocaleString('en-JM')}; ${kg(lot.delivered_kg)} delivered` : 'No capacity report yet'}>{lot.reported_capacity_kg === null ? '—' : kg(Math.max(Number(lot.reported_capacity_kg) - Number(lot.delivered_kg), 0))}</td>
                    <td className={`text-right ${lot.reported_capacity_kg !== null && Number(lot.reported_capacity_kg) < Number(lot.reserved_quantity_kg) ? 'text-destructive' : ''}`}>{kg(lot.reserved_quantity_kg)}</td>
                    <td className="pl-3"><VerificationPill state={lot.capacity_verification} />{lot.provenance_source && <span className="block text-[11px] text-muted-foreground">{lot.provenance_source} · {lot.attestation_method}</span>}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>
          </LoadState>
        </section>
      </div>
      <div className="space-y-6">
        <section aria-labelledby="new-supplier" className="operational-panel p-5">
          <h2 id="new-supplier" className="text-base font-semibold">Add a supplier</h2>
          <form className="mt-3 space-y-3" onSubmit={onFarmer}>
            <Field label="Farmer name" name="name" required minLength={2} />
            <Field label="Parish" name="parish" required />
            <Field label="Contact phone" name="contact_phone" />
            <SubmitButton busy={createFarmer.isPending}>Add supplier</SubmitButton>
            <ErrorNote error={createFarmer.error} />
          </form>
        </section>
        <section aria-labelledby="new-lot" className="operational-panel p-5">
          <h2 id="new-lot" className="text-base font-semibold">Record a declared lot</h2>
          <p className="mt-1 text-xs text-muted-foreground">You are recording the farmer&apos;s declaration on their behalf. Say how you received it.</p>
          <form className="mt-3 space-y-3" onSubmit={onLot}>
            <Select label="Supplier" name="farmer_id" required placeholder="Choose a supplier" options={(farmers.data ?? []).map(f => ({ value: f.id, label: `${f.name} (${f.parish})` }))} />
            <Select label="Crop" name="crop" required placeholder="Choose a crop" options={(crops.data ?? []).filter(c => c.active).map(c => ({ value: c.code, label: c.name }))} />
            <Select label="Expected grade" name="quality_grade_estimate" required options={[{ value: 'A', label: 'Grade A' }, { value: 'B', label: 'Grade B' }]} />
            <div className="grid grid-cols-2 gap-3"><Field label="Harvest from" name="harvest_start" type="date" required /><Field label="Harvest to" name="harvest_end" type="date" required /></div>
            <div className="grid grid-cols-2 gap-3"><Field label="Expected harvest (kg)" name="expected_quantity_kg" type="number" min="0.001" step="0.001" required /><Field label="Available now (kg)" name="available_quantity_kg" type="number" min="0" step="0.001" required /></div>
            <Field label="Farmgate price (J$/kg)" name="farmgate_price_per_kg_jmd" type="number" min="0" step="0.01" hint="Needed for cost estimates in supply proposals." />
            <Field label="How you received this" name="provenance_source" required minLength={3} placeholder="e.g. phone call with farmer" />
            <Field label="Attestation" name="attestation_method" required minLength={3} placeholder="e.g. verbal, signed form, photo" />
            <Field label="Evidence reference" name="evidence_reference" placeholder="e.g. call log entry or document number" />
            <SubmitButton busy={createLot.isPending}>Record lot</SubmitButton>
            <ErrorNote error={createLot.error} />
          </form>
        </section>
        <section aria-labelledby="relay-capacity" className="operational-panel p-5">
          <h2 id="relay-capacity" className="text-base font-semibold">Relay a capacity report</h2>
          <p className="mt-1 text-xs text-muted-foreground">Record what a farmer told you they can now supply from a lot. It is stored as their report, relayed and attested by you. A figure below what is already committed keeps the commitments on record and raises an exception; nothing is activated automatically.</p>
          <form className="mt-3 space-y-3" onSubmit={onCapacity} aria-label="Relay capacity report">
            <Select label="Lot" name="production_lot_id" required placeholder="Choose a lot" options={(lots.data ?? []).map(l => ({ value: l.id, label: `${l.farmer_name} · ${l.crop} · ${l.harvest_start}` }))} />
            <Field label="Farmer can still supply (kg)" name="reported_capacity_kg" type="number" min="0" step="0.001" required hint="Not counting anything already delivered." />
            <Field label="How the farmer told you" name="original_source" required minLength={3} placeholder="e.g. phone call with farmer" />
            <Field label="How it was attested" name="attestation_method" required minLength={3} placeholder="e.g. verbal, signed form" />
            <Field label="Evidence for this report" name="evidence_reference" placeholder="e.g. call log entry" />
            <SubmitButton busy={relay.isPending}>Record capacity report</SubmitButton>
            <ErrorNote error={relay.error} />
          </form>
        </section>
      </div>
    </div>
  </TradePage>;
}
