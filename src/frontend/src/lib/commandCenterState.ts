export type DeliveryWindowPhase = 'BEFORE' | 'IN_WINDOW' | 'ENDS_TODAY' | 'OVERDUE' | 'UNAVAILABLE';
export type ActionState = 'required' | 'review' | 'incomplete' | 'limited';

export interface ActionAssessment {
  kind: ActionState;
  title: string;
  reason: string;
}

export function classifyDeliveryWindow(start: string | null | undefined, end: string | null | undefined, now = new Date()): DeliveryWindowPhase {
  if (!isDateKey(start) || !isDateKey(end) || start > end) return 'UNAVAILABLE';
  const today = jamaicaDateKey(now);
  if (today < start) return 'BEFORE';
  if (today > end) return 'OVERDUE';
  if (today === end) return 'ENDS_TODAY';
  return 'IN_WINDOW';
}

export function windowPhaseLabel(phase: DeliveryWindowPhase) {
  switch (phase) {
    case 'BEFORE': return 'Before delivery window';
    case 'IN_WINDOW': return 'In delivery window';
    case 'ENDS_TODAY': return 'Window ends today';
    case 'OVERDUE': return 'Delivery window ended';
    case 'UNAVAILABLE': return 'Delivery window unavailable';
  }
}

export function formatDeliveryDate(value: string | null | undefined) {
  if (!isDateKey(value)) return 'Unavailable';
  const date = new Date(`${value}T00:00:00Z`);
  return new Intl.DateTimeFormat('en-JM', { dateStyle: 'medium', timeZone: 'UTC' }).format(date);
}

export function assessActionState(input: {
  supplyHealth: string | null | undefined;
  shortfallKg: number;
  riskLabel: string | null | undefined;
  windowPhase: DeliveryWindowPhase;
  dataUnavailable?: boolean;
}): ActionAssessment {
  const planningReasons: string[] = [];
  if (!input.supplyHealth) return { kind: 'incomplete', title: 'Planning status unavailable', reason: 'No authoritative supply-health state was returned.' };
  if (!Number.isFinite(input.shortfallKg)) return { kind: 'incomplete', title: 'Planning quantities unavailable', reason: 'A valid planning shortfall was not returned.' };
  if (input.supplyHealth === 'AT_RISK' || input.supplyHealth === 'ESCALATION_REQUIRED') planningReasons.push(`Planning health is ${input.supplyHealth.replace(/_/g, ' ')}.`);
  else if (input.supplyHealth !== 'COVERED') return { kind: 'incomplete', title: 'Planning status unavailable', reason: `The returned supply-health state “${input.supplyHealth}” is not recognized.` };
  if (Number.isFinite(input.shortfallKg) && input.shortfallKg > 0) planningReasons.push(`${input.shortfallKg} kg planning shortfall remains.`);
  if (input.riskLabel === 'HIGH' || input.riskLabel === 'MEDIUM') planningReasons.push(`Structural risk is ${input.riskLabel}.`);
  if (planningReasons.length) return { kind: 'required', title: 'Planning action required', reason: planningReasons.join(' ') };

  if (input.windowPhase === 'OVERDUE') return { kind: 'review', title: 'Verify fulfilment after the window', reason: 'The full delivery window has ended, but delivered, buyer-confirmed, and reconciled states are not returned by this API.' };
  if (input.windowPhase === 'ENDS_TODAY') return { kind: 'review', title: 'Verify fulfilment today', reason: 'The delivery window ends today and no authoritative receiving schedule or final delivery state is returned.' };
  if (input.windowPhase === 'UNAVAILABLE') return { kind: 'incomplete', title: 'Timing assessment unavailable', reason: 'A valid start and end date are required before due-window action can be assessed.' };
  if (input.dataUnavailable) return { kind: 'incomplete', title: 'Operational assessment incomplete', reason: 'Fulfilment or event data failed to load. Retry before relying on the current action assessment.' };
  if (!input.riskLabel || !['LOW', 'MEDIUM', 'HIGH'].includes(input.riskLabel)) return { kind: 'incomplete', title: 'Risk assessment unavailable', reason: 'No recognized structural risk snapshot was returned, so the planning assessment is incomplete.' };

  return { kind: 'limited', title: 'Action status partially assessable', reason: 'No planning or due-window trigger is visible in the returned state. The API provides no snapshot timestamp, receiving schedule, approval requirements, or unified exception queue, so current freshness and other actions cannot be confirmed. This is not an all-clear.' };
}

function isDateKey(value: string | null | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function jamaicaDateKey(date: Date) {
  if (!Number.isFinite(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Jamaica', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}