'use client';

import { useFulfilmentSites, useSiteCommands } from '@/hooks/useFulfilment';
import { ErrorNote, Field, LoadState, Pill, SubmitButton, TradePage, formValues } from '@/components/trade/TradeUi';

/** Where produce is received. Sites belong to the organization and are deactivated, never deleted. */
export function FulfilmentSites() {
  const sites = useFulfilmentSites(true);
  const { create, deactivate } = useSiteCommands();
  async function onCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const v = formValues(form);
    const ok = await create.mutateAsync({ name: v.name ?? '', node_type: v.node_type ?? '', parish: v.parish ?? '' }).then(() => true, () => false);
    if (ok) form.reset();
  }
  return <TradePage eyebrow="Fulfilment" title="Fulfilment sites" description="Packhouses, hubs and stores where your organization receives and grades produce."
    crumbs={[{ label: 'Fulfilment', href: '/fulfilment' }, { label: 'Sites' }]}>
    <section aria-labelledby="sites" className="operational-panel p-5">
      <h2 id="sites" className="text-base font-semibold">Sites</h2>
      <LoadState query={sites} empty={<p className="mt-2 text-sm text-muted-foreground">No sites yet. Add one before recording receipts.</p>}>
        <ul className="mt-3 divide-y divide-white/[0.07] text-sm" aria-label="Fulfilment sites">
          {sites.data?.map(site => <li key={site.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>{site.name}<span className="block text-xs text-muted-foreground">{site.node_type} · {site.parish}</span></span>
            <span className="flex items-center gap-2"><Pill tone={site.active ? 'good' : 'neutral'}>{site.active ? 'Active' : 'Inactive'}</Pill>
              {site.active && <button type="button" disabled={deactivate.isPending} onClick={() => deactivate.mutate({ siteId: site.id })}
                className="min-h-9 rounded-md px-3 text-xs text-muted-foreground" aria-label={`Deactivate ${site.name}`}>Deactivate</button>}</span>
          </li>)}
        </ul>
      </LoadState>
      <form onSubmit={onCreate} aria-label="Add a site" className="mt-4 grid gap-3 sm:grid-cols-4">
        <Field label="Name" name="name" required minLength={2} />
        <Field label="Type" name="node_type" required minLength={2} placeholder="e.g. packhouse" />
        <Field label="Parish" name="parish" required minLength={2} />
        <div className="self-end"><SubmitButton busy={create.isPending}>Add site</SubmitButton></div>
      </form>
      <ErrorNote error={create.error ?? deactivate.error} />
      <p className="mt-3 text-xs text-muted-foreground">An inactive site keeps its history but cannot receive new produce.</p>
    </section>
  </TradePage>;
}
