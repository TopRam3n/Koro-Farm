import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { formatJamaicaDateTime } from '@/lib/jamaica-time';
import type { FarmerRequest } from './types';

export function RequestCard({ request }: { request: FarmerRequest }) {
    return <Card><CardContent className="p-4"><div className="flex justify-between gap-3"><div><p className="font-semibold">{request.requestedKg} kg · {request.crop}</p><p className="text-sm text-muted-foreground">{request.grade} · {request.role === 'STANDBY' ? 'Standby request' : 'Fill request'}</p></div><p className="font-mono text-sm">J${request.pricePerKgJmd}/kg</p></div><div className="mt-4 space-y-1 text-sm"><p>{request.destination}</p><p className="text-muted-foreground">Collect {formatJamaicaDateTime(request.collectionAt)}</p><p className="font-medium text-warning">Respond by {formatJamaicaDateTime(request.responseExpiresAt)}</p></div><Button asChild className="mt-4 h-12 w-full"><Link href={`/f/requests/${request.id}`}>Review request</Link></Button></CardContent></Card>;
}
