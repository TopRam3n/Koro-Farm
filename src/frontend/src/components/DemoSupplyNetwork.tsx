'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';

type Farmer = { external_id: string; name: string; farm_name: string; crops: string[] };
type Lot = { external_id: string; crop: string; available_quantity_kg: string; harvest_start: string; harvest_end: string };

export function DemoSupplyNetwork() {
    const [farmers, setFarmers] = useState<Farmer[]>([]);
    const [lots, setLots] = useState<Lot[]>([]);
    const [error, setError] = useState('');

    useEffect(() => {
        Promise.all([
            apiFetch<{ items: Farmer[] }>('/demo-history/farmers'),
            apiFetch<{ items: Lot[] }>('/demo-history/current-inventory'),
        ]).then(([profiles, inventory]) => {
            setFarmers(profiles.items);
            setLots(inventory.items);
        }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
    }, []);

    return <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-400/20 bg-amber-400/5 p-5">
            <div><h2 className="text-lg font-semibold">Five demo farm partners</h2><p className="mt-1 text-sm text-muted-foreground">Simulated current inventory, not verified farmer stock. Historical production is separate.</p></div>
            <Link href="/demand/demo-orders" className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">Open buyer–farmer marketplace</Link>
        </div>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {farmers.map((farmer) => {
                const ownLots = lots.filter((lot) => lot.external_id === farmer.external_id);
                const total = ownLots.reduce((sum, lot) => sum + Number(lot.available_quantity_kg), 0);
                return <article key={farmer.external_id} className="operational-panel p-5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-primary">{farmer.external_id} · Demo farmer</p>
                    <h3 className="mt-2 text-xl font-semibold">{farmer.name}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">{farmer.farm_name}</p>
                    <p className="mt-4 text-xs text-muted-foreground">Assigned crops</p>
                    <p className="mt-1 text-sm">{farmer.crops.join(', ')}</p>
                    <div className="mt-4 border-t border-white/10 pt-4">
                        <p className="text-xs text-muted-foreground">Simulated current available supply</p>
                        <p className="mt-1 text-2xl font-semibold tabular-nums">{total.toLocaleString()} <span className="text-sm font-normal text-muted-foreground">kg</span></p>
                        <ul className="mt-3 space-y-2 text-sm">{ownLots.map((lot) => <li key={lot.crop} className="flex justify-between gap-4"><span>{lot.crop.split('_').join(' ')}</span><span className="tabular-nums">{Number(lot.available_quantity_kg).toLocaleString()} kg</span></li>)}</ul>
                    </div>
                </article>;
            })}
        </div>
    </div>;
}
