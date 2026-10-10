'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { requirementSteps, type RequirementDraft, type RequirementStep } from './types';
import { validateRequirementStep } from './selectors';
import { useCreateRequirement } from '@/hooks/api/useBackend';
import { ApiError } from '@/lib/api/client';

const initial: Partial<RequirementDraft> = {};
const KEY = 'korofarm.requirement-draft';

export function RequirementWizard({ step }: { step: RequirementStep }) {
    const router = useRouter(); const [draft, setDraft] = useState<Partial<RequirementDraft>>(initial); const [submitted, setSubmitted] = useState(false); const createRequirement = useCreateRequirement();
    useEffect(() => { try { const saved = sessionStorage.getItem(KEY); if (saved) setDraft(JSON.parse(saved)); } catch { sessionStorage.removeItem(KEY); } }, []);
    const update = (patch: Partial<RequirementDraft>) => { const next = { ...draft, ...patch }; setDraft(next); sessionStorage.setItem(KEY, JSON.stringify(next)); };
    const index = requirementSteps.indexOf(step); const next = requirementSteps[index + 1]; const valid = validateRequirementStep(step, draft);
    const submit = async () => { if (!valid || !draft.quantityKg || !draft.earliestAt || !draft.latestAt) return; try { await createRequirement.mutateAsync({ buyer_id: draft.destinationSiteId!, crop: 'GINGER', grade: draft.gradeId === 'grade-b-v1' ? 'B' : 'A', required_quantity_kg: draft.quantityKg, delivery_window_start: draft.earliestAt.slice(0, 10), delivery_window_end: draft.latestAt.slice(0, 10) }); sessionStorage.removeItem(KEY); setSubmitted(true); } catch { /* mutation state renders the backend error below */ } };
    if (submitted) return <div className="py-12"><h1 className="text-3xl font-semibold">Submitted for Planning</h1><p className="mt-3 text-muted-foreground">The requirement was created in KoroFarm. Supply remains unplanned until the planning workflow is run.</p><Button className="mt-6" onClick={() => router.push('/b')}>Return to portfolio</Button></div>;
    return <section className="mx-auto max-w-2xl"><p className="font-mono text-xs uppercase tracking-wider text-primary">New requirement · {index + 1} of {requirementSteps.length}</p><h1 className="mt-2 text-3xl font-semibold">{title(step)}</h1><div className="mt-6">{field(step, draft, update)}</div>{createRequirement.error && <p role="alert" className="mt-4 text-sm text-destructive">{apiErrorMessage(createRequirement.error)}</p>}<div className="mt-8 flex justify-between border-t pt-5"><Button variant="ghost" onClick={() => index ? router.push(`/b/requirements/new/${requirementSteps[index - 1]}`) : router.push('/b')}>Back</Button>{step === 'review' ? <Button disabled={!valid || createRequirement.isPending} onClick={submit}>{createRequirement.isPending ? 'Submitting…' : 'Submit for Planning'}</Button> : <Button disabled={!valid} onClick={() => router.push(`/b/requirements/new/${next}`)}>Continue</Button>}</div></section>;
}

function apiErrorMessage(error: Error) { if (error instanceof ApiError && error.status === 0) return 'Cannot reach the KoroFarm backend. Check NEXT_PUBLIC_BACKEND_URL and that the API is running.'; if (error instanceof ApiError && error.status === 401) return 'Your session is not authorized by the KoroFarm backend. Please sign in again.'; return 'The requirement could not be created. Your draft has been kept so you can retry.'; }

function title(step: RequirementStep) { return ({ crop: 'Crop', grade: 'Grade / specification', volume: 'Volume', window: 'Delivery window', destination: 'Destination site', commercial: 'Commercial constraints', review: 'Review requirement' })[step]; }
function field(step: RequirementStep, d: Partial<RequirementDraft>, update: (p: Partial<RequirementDraft>) => void) {
    if (step === 'crop') return <Choice label="Choose crop" options={[['crop-ginger', 'Fresh ginger']]} value={d.cropTaxonomyId} onChange={(id, label) => update({ cropTaxonomyId: id, cropLabel: label })} />;
    if (step === 'grade') return <Choice label="Choose specification" options={[['grade-a-v1', 'Grade A'], ['grade-b-v1', 'Grade B']]} value={d.gradeId} onChange={(id, label) => update({ gradeId: id, gradeLabel: label })} />;
    if (step === 'volume') return <div><Label htmlFor="kg">Required quantity (kg)</Label><Input id="kg" type="number" min="1" value={d.quantityKg || ''} onChange={e => update({ quantityKg: Number(e.target.value), enteredUnit: 'kg' })} /></div>;
    if (step === 'window') return <div className="grid gap-4 sm:grid-cols-2"><div><Label>Earliest delivery</Label><Input type="datetime-local" value={d.earliestAt || ''} onChange={e => update({ earliestAt: e.target.value })} /></div><div><Label>Latest delivery</Label><Input type="datetime-local" value={d.latestAt || ''} onChange={e => update({ latestAt: e.target.value })} /></div></div>;
    if (step === 'destination') return <div className="space-y-4"><div><Label htmlFor="buyer-id">Buyer ID</Label><Input id="buyer-id" placeholder="Backend buyer UUID" value={d.destinationSiteId || ''} onChange={e => update({ destinationSiteId: e.target.value })} /></div><div><Label>Destination / receiving site</Label><Input placeholder="e.g. St. James Collection Hub" value={d.destinationLabel || ''} onChange={e => update({ destinationLabel: e.target.value })} /></div><Label>Receiving constraints</Label><Textarea value={d.receivingConstraints || ''} onChange={e => update({ receivingConstraints: e.target.value })} /></div>;
    if (step === 'commercial') return <div className="space-y-4"><div><Label>Optional price ceiling (JMD/kg)</Label><Input type="number" min="1" value={d.priceCeilingJmd || ''} onChange={e => update({ priceCeilingJmd: e.target.value ? Number(e.target.value) : undefined })} /></div><div><Label>Documentation / compliance requirements</Label><Textarea value={d.complianceRequirements || ''} onChange={e => update({ complianceRequirements: e.target.value })} /></div></div>;
    return <div className="rounded-lg border p-5 text-sm leading-7"><p><strong>{d.cropLabel}</strong> · {d.gradeLabel}</p><p>{d.quantityKg} kg</p><p>{d.earliestAt} → {d.latestAt}</p><p>{d.destinationLabel}</p><p>Price ceiling: {d.priceCeilingJmd ? `J$${d.priceCeilingJmd}/kg` : 'None specified'}</p><p className="mt-3 text-muted-foreground">Submitting requests planning; it does not claim supply is committed or fulfilled.</p></div>;
}
function Choice({ label, options, value, onChange }: { label: string; options: string[][]; value?: string; onChange: (id: string, label: string) => void }) { return <div><Label>{label}</Label><div className="mt-2 grid gap-2">{options.map(([id, text]) => <Button key={id} type="button" variant={value === id ? 'default' : 'outline'} className="h-12 justify-start" onClick={() => onChange(id, text)}>{text}</Button>)}</div></div>; }
