'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { formatJamaicaDateTime } from '@/lib/jamaica-time';
import { createRecoveryEvents, projectCoverage } from './recovery';
import type { FarmerCommitment, ShortfallReport } from './types';

export function CommitmentDetail({ commitment }: { commitment: FarmerCommitment }) {
    const [showForm, setShowForm] = useState(false); const [expectedKg, setExpectedKg] = useState('0'); const [reason, setReason] = useState<ShortfallReport['reason']>('CROP_LOSS'); const [note, setNote] = useState(''); const [events, setEvents] = useState<ReturnType<typeof createRecoveryEvents>>([]);
    const lostKg = commitment.quantityKg - Number(expectedKg);
    const submit = () => { if (!Number.isFinite(lostKg) || lostKg <= 0 || Number(expectedKg) < 0) return; setEvents(createRecoveryEvents({ commitmentId: commitment.id, expectedKg: Number(expectedKg), lostKg, reason, note })); };
    if (events.length) { const coverage = projectCoverage(events); return <section className="py-8"><p className="font-mono text-xs uppercase text-primary">Recovery episode REC-001</p><h1 className="mt-2 text-2xl font-semibold">Shortfall reported</h1><p className="mt-3 text-muted-foreground">Coverage moved {coverage.initialKg} → {coverage.disruptedKg} → {coverage.restoredKg} kg. The plan recovered; this does not claim physical fulfilment.</p><div className="mt-5 space-y-2">{events.map(event => <div key={event.id} className="rounded border p-3 text-sm"><span className="font-medium">{event.type}</span></div>)}</div><Button asChild className="mt-6"><Link href="/f/commitments">Back to commitments</Link></Button></section>; }
    return <section><Button asChild variant="ghost" className="mb-4"><Link href="/f/commitments">← Commitments</Link></Button><h1 className="text-3xl font-semibold">{commitment.quantityKg} kg {commitment.crop}</h1><Card className="mt-5"><CardContent className="grid gap-4 p-5 text-sm"><Term label="Grade" value={commitment.grade} /><Term label="Schedule" value={formatJamaicaDateTime(commitment.scheduledAt)} /><Term label="Location" value={commitment.location} /><Term label="Production lot" value={commitment.lotId} /><Term label="Commercial terms" value={`J$${commitment.pricePerKgJmd}/kg · ${commitment.paymentTerms}`} /><Term label="Role / status" value={`${commitment.role} · ${commitment.state}`} /></CardContent></Card>{!showForm ? <Button variant="destructive" className="mt-5 h-12 w-full" onClick={() => setShowForm(true)}>Report Issue / Shortfall</Button> : <div className="mt-5 space-y-4 rounded-lg border p-4"><div><Label htmlFor="expected">Quantity still expected to supply (kg)</Label><Input id="expected" type="number" min="0" max={commitment.quantityKg} value={expectedKg} onChange={e => setExpectedKg(e.target.value)} /></div><p className="text-sm">Quantity at risk/lost: <strong>{Math.max(0, lostKg)} kg</strong></p><div><Label htmlFor="reason">Reason category</Label><select id="reason" className="mt-1 h-10 w-full rounded-md border bg-background px-3" value={reason} onChange={e => setReason(e.target.value as ShortfallReport['reason'])}><option value="CROP_LOSS">Crop loss</option><option value="WEATHER">Weather</option><option value="LABOUR">Labour</option><option value="TRANSPORT">Transport</option><option value="OTHER">Other</option></select></div><div><Label htmlFor="note">Optional note / expected resolution</Label><Textarea id="note" value={note} onChange={e => setNote(e.target.value)} /></div><Button className="h-12 w-full" disabled={lostKg <= 0 || Number(expectedKg) < 0} onClick={submit}>Submit shortfall report</Button></div>}</section>;
}
function Term({ label, value }: { label: string; value: string }) { return <div><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-medium">{value}</p></div>; }
