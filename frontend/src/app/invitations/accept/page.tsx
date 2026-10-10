'use client';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAcceptInvitation } from '@/hooks/api/useBackend';

export default function AcceptInvitation() {
    const [token, setToken] = useState('');
    const accept = useAcceptInvitation();
    useEffect(() => { setToken(new URLSearchParams(window.location.search).get('token') ?? ''); }, []);
    return <main className="mx-auto flex min-h-screen max-w-lg items-center p-5"><Card className="w-full"><CardHeader><CardTitle>Accept KoroFarm invitation</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-muted-foreground">Accept your organization invitation using the secure token from your invitation.</p><Input aria-label="Invitation token" value={token} onChange={e => setToken(e.target.value)} placeholder="Invitation token" /><Button className="w-full" disabled={!token || accept.isPending || accept.isSuccess} onClick={() => accept.mutate(token)}>{accept.isPending ? 'Accepting…' : accept.isSuccess ? 'Invitation accepted' : accept.isError ? 'Retry acceptance' : 'Accept invitation'}</Button>{accept.isError && <p role="alert" className="text-sm text-destructive">The invitation could not be accepted. It may be invalid or expired; a retry reuses the same action key.</p>}{accept.isSuccess && <p role="status" className="text-sm text-emerald-700">Invitation accepted. You can now sign in to your workspace.</p>}</CardContent></Card></main>;
}
