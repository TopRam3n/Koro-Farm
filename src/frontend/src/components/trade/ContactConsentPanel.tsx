'use client';

import { useState } from 'react';
import { useConsents, useRecordConsent } from '@/hooks/useNotifications';
import { useCan } from '@/hooks/useIdentity';
import { ErrorNote, Field, LoadState, Pill, Select, SubmitButton, formValues, humanize } from '@/components/trade/TradeUi';

const PURPOSES = [
  ['SUPPLY_REQUESTS', 'Supply requests, reminders and reply dates'],
  ['RELEASE_AGREEMENTS', 'Release agreements'],
] as const;

/** Record a supplier's consent to be contacted outside the app, or its withdrawal (R1 WP5, M3). Nothing is sent from
 *  here: messages go out only through the notification service, and only with a current consent for their purpose. */
export function ContactConsentPanel({ farmers }: { farmers: Array<{ id: string; name: string }> }) {
  const can = useCan();
  const [farmerId, setFarmerId] = useState('');
  const consents = useConsents('farmers', farmerId || null);
  const record = useRecordConsent('farmers', farmerId);
  const [granted, setGranted] = useState('yes');
  if (!can('supply.view')) return null;
  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const v = formValues(form);
    const purposes = PURPOSES.map(([key]) => key).filter(key => (form.elements.namedItem(key) as HTMLInputElement | null)?.checked);
    const ok = await record.mutateAsync({ channel: v.channel, address: v.address, granted: granted === 'yes', purposes: granted === 'yes' ? purposes : [],
      wording_version: v.wording_version, how_given: v.how_given, evidence_reference: v.evidence_reference || null }).then(() => true, () => false);
    if (ok) form.reset();
  }
  return <section aria-labelledby="contact-consent" className="operational-panel p-5">
    <h2 id="contact-consent" className="text-base font-semibold">Consent to be contacted</h2>
    <p className="mt-1 text-xs text-muted-foreground">Messages outside the app go only to suppliers whose current consent covers them. No messaging provider is connected yet: messages are recorded, not sent.</p>
    <div className="mt-3 max-w-sm"><Select label="Supplier whose consent to show" name="consent_farmer" value={farmerId} onChange={event => setFarmerId(event.target.value)} placeholder="Choose a supplier"
      options={farmers.map(f => ({ value: f.id, label: f.name }))} /></div>
    {farmerId && <LoadState query={consents} empty={<p className="mt-3 text-sm text-muted-foreground">No consent recorded. This supplier will not be contacted outside the app.</p>}>
      <ul className="mt-3 space-y-2 text-sm" aria-label="Consent history">{consents.data?.map((c, index) => <li key={c.id} data-consent={c.state} className="rounded-md border border-white/[0.1] p-3">
        <div className="flex flex-wrap items-center gap-2"><Pill tone={c.state === 'GRANTED' ? 'good' : 'neutral'}>{humanize(c.state)}</Pill>
          <span>{c.channel} {c.address}</span>{index === 0 && <span className="text-xs text-muted-foreground">current</span>}</div>
        <p className="mt-1 text-xs text-muted-foreground">{c.purposes.map(p => humanize(p)).join(', ') || 'No purposes'} · wording {c.wording_version} · {c.how_given} · {new Date(c.created_at).toLocaleString('en-JM')}</p>
      </li>)}</ul>
    </LoadState>}
    {farmerId && can('supply.manage') && <form onSubmit={onSubmit} aria-label="Record contact consent" className="mt-4 grid gap-3 sm:grid-cols-2">
      <Select label="Consent decision" name="granted" value={granted} onChange={event => setGranted(event.target.value)}
        options={[{ value: 'yes', label: 'Agrees to be contacted' }, { value: 'no', label: 'Withdraws consent' }]} />
      <Select label="Contact channel" name="channel" required options={['SMS', 'WHATSAPP', 'EMAIL'].map(c => ({ value: c, label: c === 'WHATSAPP' ? 'WhatsApp' : c === 'EMAIL' ? 'Email' : 'SMS' }))} />
      <Field label="Number or address" name="address" required minLength={3} />
      <Field label="Consent wording version" name="wording_version" required placeholder="e.g. draft-2026-11" />
      <Field label="How consent was given" name="how_given" required minLength={3} placeholder="e.g. signed form, recorded call" />
      <Field label="Consent evidence reference" name="evidence_reference" placeholder="e.g. form number" />
      {granted === 'yes' && <fieldset className="sm:col-span-2"><legend className="text-xs text-muted-foreground">Agreed to be contacted about</legend>
        {PURPOSES.map(([key, label]) => <label key={key} className="mt-1 flex items-center gap-2 text-sm"><input type="checkbox" name={key} defaultChecked={key === 'SUPPLY_REQUESTS'} />{label}</label>)}
      </fieldset>}
      <div className="sm:col-span-2"><SubmitButton busy={record.isPending}>Record</SubmitButton></div>
    </form>}
    <ErrorNote error={record.error} />
  </section>;
}
