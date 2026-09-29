import Link from 'next/link';
import { Search } from 'lucide-react';
import { StatusBadge } from '@/components/StatusBadge';
import type { AssuranceResponse } from '@/hooks/useAssurance';

type Props = {
  data: AssuranceResponse;
  required: number;
  committed: number;
  standby: number;
  coverage: number;
  mode: 'programmes' | 'demand';
};

export function ResponsiveRequirementTable({ data, required, committed, standby, coverage, mode }: Props) {
  const reference = mode === 'programmes' ? 'GINGER-PROGRAMME' : data.requirement.id.slice(0, 13);
  const commodity = `Grade ${data.requirement.grade} ${data.requirement.crop}`;
  const rows = [
    ['Reference', reference],
    ['Buyer', data.requirement.buyer_name],
    ['Commodity', commodity],
    ['Required', `${required} kg`],
    ['Committed', `${committed} kg`],
    ['Standby', `${standby} kg`],
    ['Coverage', `${coverage}%`],
    ['Delivery', data.requirement.delivery_window_start],
  ];

  return <section className="operational-panel overflow-hidden" aria-labelledby="requirement-table-title">
    <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
      <p id="requirement-table-title" className="text-xs text-muted-foreground">1 configured {mode === 'programmes' ? 'programme' : 'requirement'}</p>
      <span className="flex items-center gap-2 text-xs text-muted-foreground"><Search className="h-3.5 w-3.5" />Search unavailable across unlisted records</span>
    </div>
    <dl className="divide-y divide-white/[0.07] md:hidden">
      {rows.map(([label, value]) => <div key={label} className="flex items-start justify-between gap-5 px-5 py-3 text-sm"><dt className="text-muted-foreground">{label}</dt><dd className="tabular max-w-[65%] text-right font-medium">{label === 'Reference' ? <Link className="font-mono text-xs text-primary hover:underline" href={`/requirements/${data.requirement.id}`}>{value}</Link> : value}</dd></div>)}
      <div className="flex items-center justify-between gap-5 px-5 py-3 text-sm"><dt className="text-muted-foreground">Status</dt><dd><StatusBadge status={data.supply_health} /></dd></div>
    </dl>
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead className="text-[10px] uppercase tracking-wider text-muted-foreground"><tr>{['Reference', 'Buyer', 'Commodity', 'Required', 'Committed', 'Standby', 'Coverage', 'Status', 'Delivery'].map(label => <th key={label} className="border-b border-white/[0.07] px-4 py-3 font-medium">{label}</th>)}</tr></thead>
        <tbody><tr><td className="px-4 py-4"><Link className="font-mono text-xs text-primary hover:underline" href={`/requirements/${data.requirement.id}`}>{reference}</Link></td><td className="px-4 py-4">{data.requirement.buyer_name}</td><td className="px-4 py-4">{commodity}</td><td className="tabular px-4 py-4">{required} kg</td><td className="tabular px-4 py-4">{committed} kg</td><td className="tabular px-4 py-4 text-accent">{standby} kg</td><td className="tabular px-4 py-4">{coverage}%</td><td className="px-4 py-4"><StatusBadge status={data.supply_health} /></td><td className="px-4 py-4 text-xs text-muted-foreground">{data.requirement.delivery_window_start}</td></tr></tbody>
      </table>
    </div>
    <p className="border-t border-white/[0.07] px-5 py-4 text-xs text-muted-foreground">A complete registry requires a backend list endpoint. This view does not invent unlisted records.</p>
  </section>;
}
