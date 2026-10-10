'use client';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorState, LoadingState } from '@/components/production/PageState';
import { useSublotTraceability } from '@/hooks/api/useBackend';

export default function SublotTraceability() {
    const id = String(useParams<{ id: string }>().id);
    const q = useSublotTraceability(id);
    if (q.isLoading) return <LoadingState label="Loading sublot traceability…" />;
    if (q.error) return <ErrorState message="The traceability chain could not be loaded." onRetry={() => void q.refetch()} />;
    return <section className="space-y-6"><div><p className="font-mono text-xs uppercase text-primary">Evidence chain</p><h1 className="mt-2 text-3xl font-semibold">Sublot {id.slice(0, 8)}</h1><p className="mt-2 text-sm text-muted-foreground">Authoritative farmer → production lot → allocation → received sublot traceability.</p></div><Card><CardHeader><CardTitle>Traceability record</CardTitle></CardHeader><CardContent><pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-xs">{JSON.stringify(q.data ?? {}, null, 2)}</pre></CardContent></Card></section>;
}
