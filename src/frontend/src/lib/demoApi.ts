const requirementId = '00000000-0000-0000-0000-000000000500';

const baseAllocations = [
  ...Array.from({ length: 6 }, (_, index) => ({ id: `demo-c${index + 1}`, production_lot_id: `demo-lot-${index + 1}`, farmer_id: `demo-farmer-${index + 1}`, farmer_name: `Demo Farmer ${index + 1}`, parish: ['Manchester', 'St. Elizabeth', 'Clarendon', 'St. Ann'][index % 4], role: 'COMMITTED', status: 'COMMITTED', quantity_kg: '80.000' })),
  { id: 'demo-c7', production_lot_id: 'demo-lot-7', farmer_id: 'demo-farmer-7', farmer_name: 'Demo Farmer 7', parish: 'Clarendon', role: 'COMMITTED', status: 'COMMITTED', quantity_kg: '20.000' },
  { id: 'demo-s1', production_lot_id: 'demo-lot-7', farmer_id: 'demo-farmer-7', farmer_name: 'Demo Farmer 7', parish: 'Clarendon', role: 'STANDBY', status: 'STANDBY', quantity_kg: '60.000' },
  { id: 'demo-s2', production_lot_id: 'demo-lot-8', farmer_id: 'demo-farmer-8', farmer_name: 'Demo Farmer 8', parish: 'St. Ann', role: 'STANDBY', status: 'STANDBY', quantity_kg: '40.000' },
];

let phase: 'initial' | 'risk' | 'restored' = 'initial';

export function resetDemoState() { phase = 'initial'; }

function assurance() {
  const atRisk = phase === 'risk';
  const restored = phase === 'restored';
  const allocations = baseAllocations.map((item) => ({ ...item }));
  if (atRisk || restored) allocations[0].status = 'LOST';
  if (restored) {
    allocations[7].status = 'ACTIVATED';
    allocations[8].quantity_kg = '20.000';
    allocations.push(
      { ...allocations[7], id: 'demo-r1', role: 'COMMITTED', status: 'COMMITTED', quantity_kg: '60.000' },
      { ...allocations[8], id: 'demo-r2', role: 'COMMITTED', status: 'COMMITTED', quantity_kg: '20.000' },
    );
  }
  return {
    requirement: { id: requirementId, crop: 'GINGER', grade: 'A', required_quantity_kg: '500.000', lifecycle_status: 'ACTIVE', supply_health: atRisk ? 'AT_RISK' : 'COVERED', plan_version: restored ? 2 : 1, buyer_name: 'Harbour View Hotel (Synthetic)', buyer_type: 'HOTEL', destination: 'Montego Bay, Jamaica', delivery_window_start: '2026-09-08', delivery_window_end: '2026-09-15' },
    supply_health: atRisk ? 'AT_RISK' : 'COVERED',
    committed_quantity_kg: atRisk ? '420.000' : '500.000',
    assured_coverage_quantity_kg: atRisk ? '420.000' : '500.000',
    standby_quantity_kg: restored ? '20.000' : '100.000',
    unfilled_quantity_kg: atRisk ? '80.000' : '0.000',
    committed_farmer_count: atRisk ? 6 : 7, standby_farmer_count: restored ? 1 : 2,
    parish_concentration: {}, total_landed_cost_jmd: restored ? '168626.40' : '166586.40', landed_cost_per_kg_jmd: '333.17',
    allocations,
    latest_disruption: atRisk || restored ? { lost_kg: '80.000', cause: 'competition_demo_dropout' } : null,
    latest_recovery: atRisk ? { status: 'running', standby_activated_kg: '0.000', new_supply_accepted_kg: '0.000', remaining_shortfall_kg: '80.000' } : restored ? { status: 'completed', standby_activated_kg: '80.000', new_supply_accepted_kg: '0.000', remaining_shortfall_kg: '0.000' } : null,
    economics: restored ? { original_landed_cost_jmd: '166586.40', recovered_landed_cost_jmd: '168626.40', recovery_premium_jmd: '2040.00', recovery_premium_per_kg_jmd: '4.08', recovery_premium_pct: '1.2246' } : null,
    risk: { label: restored ? 'MEDIUM' : 'LOW', rules_triggered: [], calculation_version: 'risk-v1' },
  };
}

export async function demoApiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method ?? 'GET';
  if (path.endsWith('/assurance')) return structuredClone(assurance()) as T;
  if (path.endsWith('/fulfilment')) return { required_kg: '500.000', committed_kg: assurance().committed_quantity_kg, received_kg: '0.000', accepted_kg: '0.000', rejected_kg: '0.000', accepted_shortfall_kg: '500.000' } as T;
  if (path.endsWith('/events')) {
    const events: Array<{ id: string; event_type: string; actor_type: string; payload: Record<string, string>; occurred_at: string }> = [{ id: 'demo-e1', event_type: 'plan.created', actor_type: 'planner', payload: { committed_kg: '500.000', standby_kg: '100.000' }, occurred_at: '2026-09-05T14:00:00Z' }];
    if (phase !== 'initial') events.push({ id: 'demo-e2', event_type: 'allocation.lost', actor_type: 'agent', payload: { quantity_kg: '80.000' }, occurred_at: '2026-09-05T14:01:00Z' });
    if (phase === 'restored') events.push({ id: 'demo-e3', event_type: 'recovery.completed', actor_type: 'agent', payload: { standby_activated_kg: '80.000' }, occurred_at: '2026-09-05T14:02:00Z' });
    return events as T;
  }
  if (method === 'POST' && path.includes('/dropout')) { phase = 'risk'; return { committed_kg: '420.000', supply_health: 'AT_RISK' } as T; }
  if (method === 'POST' && path.endsWith('/recovery')) { phase = 'restored'; return { committed_kg: '500.000', supply_health: 'COVERED' } as T; }
  throw new Error(`Demo mode does not implement ${method} ${path}`);
}
