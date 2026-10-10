const requirementId = '00000000-0000-0000-0000-000000000500';

const baseAllocations = [
  ...Array.from({ length: 6 }, (_, index) => ({ id: `demo-c${index + 1}`, production_lot_id: `demo-lot-${index + 1}`, farmer_id: `demo-farmer-${index + 1}`, farmer_name: `Demo Farmer ${index + 1}`, parish: ['Manchester', 'St. Elizabeth', 'Clarendon', 'St. Ann'][index % 4], role: 'COMMITTED', status: 'COMMITTED', quantity_kg: '80.000' })),
  { id: 'demo-c7', production_lot_id: 'demo-lot-7', farmer_id: 'demo-farmer-7', farmer_name: 'Demo Farmer 7', parish: 'Clarendon', role: 'COMMITTED', status: 'COMMITTED', quantity_kg: '20.000' },
  { id: 'demo-s1', production_lot_id: 'demo-lot-7', farmer_id: 'demo-farmer-7', farmer_name: 'Demo Farmer 7', parish: 'Clarendon', role: 'STANDBY', status: 'STANDBY', quantity_kg: '60.000' },
  { id: 'demo-s2', production_lot_id: 'demo-lot-8', farmer_id: 'demo-farmer-8', farmer_name: 'Demo Farmer 8', parish: 'St. Ann', role: 'STANDBY', status: 'STANDBY', quantity_kg: '40.000' },
];

let phase: 'initial' | 'risk' | 'restored' = 'initial';

type DemoLot = {
  id: string; farmer_id: string; farmer_name: string; parish: string; crop: string;
  harvest_start: string; harvest_end: string; expected_quantity_kg: string;
  available_quantity_kg: string; reserved_quantity_kg: string; quality_grade_estimate: string;
  availability_confidence: string; status: string; last_verified_at: string; version: number;
};

const demoLots: DemoLot[] = [
  { id: 'demo-market-ginger', farmer_id: 'demo-farmer-1', farmer_name: 'Grace Campbell', parish: 'St. Mary', crop: 'GINGER', harvest_start: '2026-10-12', harvest_end: '2026-10-24', expected_quantity_kg: '80.000', available_quantity_kg: '80.000', reserved_quantity_kg: '0.000', quality_grade_estimate: 'A', availability_confidence: 'MEDIUM', status: 'AVAILABLE', last_verified_at: '2026-10-08T12:00:00Z', version: 1 },
  { id: 'demo-market-yam', farmer_id: 'demo-farmer-2', farmer_name: 'Leon Brown', parish: 'St. Elizabeth', crop: 'YAM', harvest_start: '2026-10-15', harvest_end: '2026-10-29', expected_quantity_kg: '120.000', available_quantity_kg: '120.000', reserved_quantity_kg: '0.000', quality_grade_estimate: 'B', availability_confidence: 'LOW', status: 'AVAILABLE', last_verified_at: '2026-10-08T12:00:00Z', version: 1 },
  { id: 'demo-market-plantain', farmer_id: 'demo-farmer-3', farmer_name: 'Marcia Reid', parish: 'Clarendon', crop: 'PLANTAIN', harvest_start: '2026-10-18', harvest_end: '2026-10-30', expected_quantity_kg: '65.000', available_quantity_kg: '65.000', reserved_quantity_kg: '0.000', quality_grade_estimate: 'A', availability_confidence: 'MEDIUM', status: 'AVAILABLE', last_verified_at: '2026-10-08T12:00:00Z', version: 1 },
];

const demoOrders: Array<{ id: string; production_lot_id: string; farmer_name: string; parish: string; crop: string; quantity_kg: string; status: string; created_at: string }> = [];
const demoWatches: Array<{ id: string; crop: string; minimum_quantity_kg: number }> = [];
const demoAlerts: Array<{ id: string; watch_id: string; production_lot_id: string; crop: string; minimum_quantity_kg: string; available_quantity_kg: string; farmer_name: string; parish: string; quality_grade_estimate: string; created_at: string; read: boolean }> = [];

function demoRole() { return process.env.NEXT_PUBLIC_DEMO_ROLE ?? 'SUPPLY_COORDINATOR'; }

function assertDemoRole(allowed: string[]) {
  if (!allowed.includes(demoRole())) throw new Error('This workspace is not available for the selected demo role.');
}

function demoAvailability(lot: DemoLot) {
  return {
    production_lot_id: lot.id, farmer_id: lot.farmer_id, farmer_name: lot.farmer_name,
    parish: lot.parish, crop: lot.crop, quality_grade_estimate: lot.quality_grade_estimate,
    harvest_start: lot.harvest_start, harvest_end: lot.harvest_end,
    expected_quantity_kg: lot.expected_quantity_kg,
    available_quantity_kg: (Number(lot.available_quantity_kg) - Number(lot.reserved_quantity_kg)).toFixed(3),
    availability_confidence: lot.availability_confidence, last_reported_at: lot.last_verified_at,
  };
}

function demoRequestBody<T>(options: RequestInit): T {
  return options.body ? JSON.parse(String(options.body)) as T : {} as T;
}

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
  if (path === '/me') return {
    id: `demo-${demoRole().toLowerCase()}`, email: `${demoRole().toLowerCase()}@demo.korofarm.test`, name: 'Demo account',
    active_organization_id: 'demo-organization', active_role: demoRole(),
    active_farmer_id: demoRole() === 'FARMER' ? 'demo-farmer-self' : null,
    active_buyer_id: demoRole() === 'BUYER' ? 'demo-buyer' : null,
  } as T;
  if (path === '/production-lots' && method === 'GET') {
    const lots = demoRole() === 'FARMER' ? demoLots.filter(lot => lot.farmer_id === 'demo-farmer-self') : demoLots;
    return lots.map(lot => ({
      id: lot.id, farmer_id: lot.farmer_id, crop: lot.crop, harvest_start: lot.harvest_start,
      harvest_end: lot.harvest_end, expected_quantity_kg: lot.expected_quantity_kg,
      available_quantity_kg: lot.available_quantity_kg, reserved_quantity_kg: lot.reserved_quantity_kg,
      quality_grade_estimate: lot.quality_grade_estimate, availability_confidence: lot.availability_confidence,
      parish: lot.parish, status: lot.status, last_verified_at: lot.last_verified_at, version: lot.version,
    })) as T;
  }
  if (path === '/v1/ingestion/farmer-production-lots' && method === 'POST') {
    assertDemoRole(['FARMER']);
    const payload = demoRequestBody<{ crop: string; harvest_start: string; harvest_end: string; expected_quantity_kg: string; quality_grade_estimate: string }>(options);
    const lot: DemoLot = {
      id: `demo-farmer-report-${Date.now()}`, farmer_id: 'demo-farmer-self', farmer_name: 'My Demo Farm', parish: 'St. Mary',
      crop: payload.crop, harvest_start: payload.harvest_start, harvest_end: payload.harvest_end,
      expected_quantity_kg: Number(payload.expected_quantity_kg).toFixed(3),
      available_quantity_kg: '0.000', reserved_quantity_kg: '0.000',
      quality_grade_estimate: payload.quality_grade_estimate, availability_confidence: 'LOW', status: 'UNAVAILABLE',
      last_verified_at: new Date().toISOString(), version: 1,
    };
    demoLots.unshift(lot);
    return { production_lot_id: lot.id, ingestion_record_id: `demo-ingestion-${Date.now()}`, verification_status: 'SELF_REPORTED', availability_confidence: 'LOW' } as T;
  }
  const farmerAvailability = path.match(/^\/v1\/ingestion\/farmer-production-lots\/([^/]+)\/availability$/);
  if (farmerAvailability && method === 'POST') {
    assertDemoRole(['FARMER']);
    const lot = demoLots.find(item => item.id === farmerAvailability[1] && item.farmer_id === 'demo-farmer-self');
    if (!lot) throw new Error('production lot not found');
    const payload = demoRequestBody<{ available_quantity_kg: string }>(options);
    const quantity = Number(payload.available_quantity_kg);
    if (quantity < Number(lot.reserved_quantity_kg) || quantity > Number(lot.expected_quantity_kg)) {
      throw new Error('ready quantity must be between reserved stock and expected harvest');
    }
    lot.available_quantity_kg = quantity.toFixed(3);
    lot.status = quantity > Number(lot.reserved_quantity_kg) ? 'AVAILABLE' : 'UNAVAILABLE';
    lot.last_verified_at = new Date().toISOString();
    lot.version += 1;
    return { production_lot_id: lot.id, ingestion_record_id: `demo-ingestion-${Date.now()}`, available_quantity_kg: lot.available_quantity_kg, status: lot.status, verification_status: 'SELF_REPORTED' } as T;
  }
  if (path.startsWith('/marketplace/availability') && method === 'GET') {
    assertDemoRole(['BUYER', 'PLATFORM_ADMIN']);
    const query = path.split('?')[1];
    const crop = query ? new URLSearchParams(query).get('crop') : null;
    const items = demoLots.filter(lot => Number(lot.available_quantity_kg) > Number(lot.reserved_quantity_kg))
      .filter(lot => !crop || lot.crop === crop).map(demoAvailability);
    return { items } as T;
  }
  if (path === '/marketplace/orders' && method === 'GET') {
    assertDemoRole(['BUYER', 'PLATFORM_ADMIN']);
    return { items: [...demoOrders] } as T;
  }
  if (path === '/marketplace/orders' && method === 'POST') {
    assertDemoRole(['BUYER', 'PLATFORM_ADMIN']);
    const payload = demoRequestBody<{ production_lot_id: string; quantity_kg: string }>(options);
    const lot = demoLots.find(item => item.id === payload.production_lot_id);
    if (!lot || lot.status !== 'AVAILABLE') throw new Error('available production lot not found');
    const quantity = Number(payload.quantity_kg);
    const remaining = Number(lot.available_quantity_kg) - Number(lot.reserved_quantity_kg);
    if (quantity <= 0 || quantity > remaining) throw new Error(`only ${remaining.toFixed(3)} kg remains available`);
    lot.reserved_quantity_kg = (Number(lot.reserved_quantity_kg) + quantity).toFixed(3);
    lot.version += 1;
    const order = { id: `demo-order-${Date.now()}`, production_lot_id: lot.id, farmer_name: lot.farmer_name, parish: lot.parish, crop: lot.crop, quantity_kg: quantity.toFixed(3), status: 'PLACED', created_at: new Date().toISOString() };
    demoOrders.unshift(order);
    return order as T;
  }
  if (path === '/marketplace/watches' && method === 'POST') {
    assertDemoRole(['BUYER', 'PLATFORM_ADMIN']);
    const payload = demoRequestBody<{ crop: string; minimum_quantity_kg: string }>(options);
    const watch = { id: `demo-watch-${Date.now()}`, crop: payload.crop, minimum_quantity_kg: Number(payload.minimum_quantity_kg) };
    demoWatches.push(watch);
    return { ...watch, minimum_quantity_kg: String(watch.minimum_quantity_kg), active: true } as T;
  }
  if (path === '/marketplace/alerts' && method === 'GET') {
    assertDemoRole(['BUYER', 'PLATFORM_ADMIN']);
    for (const watch of demoWatches) {
      for (const lot of demoLots.filter(item => item.crop === watch.crop && Number(item.available_quantity_kg) - Number(item.reserved_quantity_kg) >= watch.minimum_quantity_kg)) {
        const existing = demoAlerts.find(alert => alert.watch_id === watch.id && alert.production_lot_id === lot.id);
        if (existing) {
          existing.available_quantity_kg = (Number(lot.available_quantity_kg) - Number(lot.reserved_quantity_kg)).toFixed(3);
        } else {
          demoAlerts.unshift({ id: `demo-alert-${Date.now()}-${demoAlerts.length}`, watch_id: watch.id, production_lot_id: lot.id, crop: lot.crop, minimum_quantity_kg: watch.minimum_quantity_kg.toFixed(3), available_quantity_kg: (Number(lot.available_quantity_kg) - Number(lot.reserved_quantity_kg)).toFixed(3), farmer_name: lot.farmer_name, parish: lot.parish, quality_grade_estimate: lot.quality_grade_estimate, created_at: new Date().toISOString(), read: false });
        }
      }
    }
    return { items: [...demoAlerts] } as T;
  }
  const readAlert = path.match(/^\/marketplace\/alerts\/([^/]+)\/read$/);
  if (readAlert && method === 'POST') {
    assertDemoRole(['BUYER', 'PLATFORM_ADMIN']);
    const alert = demoAlerts.find(item => item.id === readAlert[1]);
    if (!alert) throw new Error('availability alert not found');
    alert.read = true;
    return { id: alert.id, read: true } as T;
  }
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
