'use client';

import { useEffect, useMemo, useState } from 'react';
import { AuthGate } from '@/components/AuthGate';
import { apiFetch } from '@/lib/api';

type Farmer = { external_id: string; name: string; farm_name: string; crops: string[] };
type Production = { external_id: string; year: number; quarter: string; crop: string; quantity_kg: string; original_quantity: string; original_unit: string };
type Inventory = { external_id: string; crop: string; available_quantity_kg: string; harvest_start: string; harvest_end: string; simulated: boolean; verified: boolean };

function History() {
    const [farmers, setFarmers] = useState<Farmer[]>([]);
    const [production, setProduction] = useState<Production[]>([]);
    const [inventory, setInventory] = useState<Inventory[]>([]);
    const [farmer, setFarmer] = useState('F001');
    const [year, setYear] = useState('2023');
    const [error, setError] = useState('');

    useEffect(() => {
        Promise.all([
            apiFetch<{ items: Farmer[] }>('/demo-history/farmers'),
            apiFetch<{ items: Production[] }>('/demo-history/production'),
            apiFetch<{ items: Inventory[] }>('/demo-history/current-inventory'),
        ]).then(([profiles, history, available]) => { setFarmers(profiles.items); setProduction(history.items); setInventory(available.items); })
            .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'History unavailable'));
    }, []);

    const records = useMemo(() => production.filter((item) => item.external_id === farmer && item.year === Number(year)), [production, farmer, year]);
    const totals = useMemo(() => records.reduce<Record<string, number>>((result, item) => {
        result[item.crop] = (result[item.crop] ?? 0) + Number(item.quantity_kg);
        return result;
    }, {}), [records]);

    return <main className="mx-auto max-w-5xl space-y-6 p-8">
        <h1 className="text-3xl font-bold">Simulated quarterly production history, 2023–2025</h1>
        <p className="text-sm text-amber-700">Demo dataset insights only. These national-total allocations are simulated, not verified farmer output, current stock, or forecasts.</p>
        {error && <p role="alert">{error}</p>}
        <div className="flex flex-wrap gap-4">
            <label>Demo farmer <select aria-label="Demo farmer" value={farmer} onChange={(event) => setFarmer(event.target.value)} className="ml-2 rounded border p-2">
                {farmers.map((profile) => <option value={profile.external_id} key={profile.external_id}>{profile.external_id} — {profile.name}</option>)}
            </select></label>
            <label>Year <select aria-label="Production year" className="ml-2 rounded border p-2" value={year} onChange={(event) => setYear(event.target.value)}>
                {[2023, 2024, 2025].map((value) => <option key={value}>{value}</option>)}
            </select></label>
        </div>
        <p>Assigned crops: {farmers.find((item) => item.external_id === farmer)?.crops.join(', ') ?? 'Loading…'}</p>
        <section><h2 className="text-xl font-semibold">Simulated current inventory (not farmer-confirmed)</h2>
            <p className="text-sm">These manually seeded demo quantities are separate from historical production and are not verified stock.</p>
            <ul className="mt-2 space-y-1">{inventory.filter((lot) => lot.external_id === farmer).map((lot) =>
                <li key={lot.crop}>{lot.crop.replace(/_/g, ' ')}: {Number(lot.available_quantity_kg).toLocaleString()} kg, simulated available; {lot.harvest_start} to {lot.harvest_end}</li>)}</ul>
        </section>
        <section><h2 className="text-xl font-semibold">Simulated annual totals (kg)</h2>
            <ul className="mt-2 space-y-1">{Object.entries(totals).map(([crop, amount]) => <li key={crop}>{crop}: {amount.toLocaleString()} kg</li>)}</ul>
        </section>
        <section className="overflow-x-auto"><h2 className="text-xl font-semibold">Simulated quarterly allocations</h2>
            <table className="mt-2 w-full text-left"><thead><tr><th>Quarter</th><th>Crop</th><th>Source tonnes</th><th>Normalized kg</th></tr></thead>
                <tbody>{records.map((row) => <tr className="border-t" key={`${row.year}-${row.quarter}-${row.crop}`}>
                    <td>{row.quarter}</td><td>{row.crop}</td><td>{row.original_quantity} {row.original_unit}</td><td>{Number(row.quantity_kg).toLocaleString()}</td>
                </tr>)}</tbody></table>
        </section>
    </main>;
}

export default function Page() { return <AuthGate><History /></AuthGate>; }
