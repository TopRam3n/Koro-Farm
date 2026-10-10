'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, CircleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { formatJamaicaDateTime } from '@/lib/jamaica-time';
import { decideRequest, isRequestExpired } from './selectors';
import type { FarmerRequest, FarmerRequestDecision } from './types';

export function RequestEvaluation({ request }: { request: FarmerRequest }) {
    const [now, setNow] = useState(() => new Date());
    const [partialKg, setPartialKg] = useState('');
    const [decision, setDecision] = useState<FarmerRequestDecision | null>(null);
    const expired = useMemo(() => isRequestExpired(request, now), [now, request]);
    useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 30_000); return () => window.clearInterval(timer); }, []);

    const accept = (kg: number) => { try { setDecision(decideRequest(request, kg, now)); } catch { setDecision(null); } };
    if (decision) return <Result decision={decision} request={request} />;

    return <div><Button asChild variant="ghost" className="mb-4"><Link href="/f"><ArrowLeft className="mr-2 h-4 w-4" />Queue</Link></Button><div className="space-y-5"><div><p className="font-mono text-xs uppercase tracking-wider text-primary">Procurement request</p><h1 className="mt-2 text-3xl font-semibold">{request.requestedKg} kg {request.crop}</h1><p className="mt-2 text-muted-foreground">{request.grade} · {request.role === 'STANDBY' ? 'Standby capacity' : 'Committed supply'}</p></div>{expired && <div className="flex gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"><CircleAlert className="h-5 w-5 shrink-0" />This request has expired and can no longer be accepted or declined.</div>}<Card><CardContent className="grid gap-4 p-5 text-sm"><Term label="Price" value={`J$${request.pricePerKgJmd}/kg · J$${(request.pricePerKgJmd * request.requestedKg).toLocaleString('en-JM')} total`} /><Term label="Collection / delivery" value={formatJamaicaDateTime(request.collectionAt)} /><Term label="Location" value={request.destination} /><Term label="Payment" value={request.paymentTerms} /><Term label="Response expires" value={formatJamaicaDateTime(request.responseExpiresAt)} /></CardContent></Card><div className="space-y-3"><Button disabled={expired} className="h-12 w-full" onClick={() => accept(request.requestedKg)}>Accept full {request.requestedKg} kg</Button><div className="rounded-lg border p-4"><Label htmlFor="partial">Accept a partial quantity (kg)</Label><div className="mt-2 flex gap-2"><Input id="partial" inputMode="decimal" value={partialKg} onChange={e => setPartialKg(e.target.value)} placeholder="e.g. 50" /><Button variant="secondary" disabled={expired || !partialKg} onClick={() => accept(Number(partialKg))}>Accept partial</Button></div></div><Button disabled={expired} variant="outline" className="h-12 w-full" onClick={() => setDecision({ type: 'DECLINE' })}>Decline request</Button><Button disabled={expired} variant="ghost" className="h-12 w-full" onClick={() => setDecision({ type: 'COORDINATOR_HELP' })}>Request coordinator help</Button></div></div></div>;
}

function Term({ label, value }: { label: string; value: string }) { return <div><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-medium">{value}</p></div>; }
function Result({ decision, request }: { decision: FarmerRequestDecision; request: FarmerRequest }) { const copy = decision.type === 'ACCEPT' ? `Accepted ${decision.acceptedKg} kg. ${decision.remainderKg ? `${decision.remainderKg} kg remains available for further planning.` : 'The full requested quantity is accepted.'}` : decision.type === 'DECLINE' ? 'Request declined.' : 'Coordinator assistance requested.'; return <div className="py-12"><h1 className="text-2xl font-semibold">Response recorded locally</h1><p className="mt-3 text-muted-foreground">{copy}</p><p className="mt-3 text-xs text-muted-foreground">Demo request {request.id}. Backend persistence is not yet available; no external action is being claimed.</p><Button asChild className="mt-6"><Link href="/f">Return to queue</Link></Button></div>; }
