import { describe, expect, it } from 'vitest';
import { assessActionState, classifyDeliveryWindow } from '@/lib/commandCenterState';

const beforeWindow = new Date('2026-09-10T17:00:00Z');
const inWindow = new Date('2026-09-12T17:00:00Z');
const windowEnd = new Date('2026-09-15T17:00:00Z');
const afterWindow = new Date('2026-09-16T17:00:00Z');

describe('Control Center delivery-window assessment', () => {
  it('uses both dates and treats the end date as inclusive', () => {
    expect(classifyDeliveryWindow('2026-09-11', '2026-09-15', beforeWindow)).toBe('BEFORE');
    expect(classifyDeliveryWindow('2026-09-11', '2026-09-15', inWindow)).toBe('IN_WINDOW');
    expect(classifyDeliveryWindow('2026-09-11', '2026-09-15', windowEnd)).toBe('ENDS_TODAY');
    expect(classifyDeliveryWindow('2026-09-11', '2026-09-15', afterWindow)).toBe('OVERDUE');
  });

  it('keeps missing or invalid windows unassessed', () => {
    expect(classifyDeliveryWindow(undefined, '2026-09-15', inWindow)).toBe('UNAVAILABLE');
    expect(classifyDeliveryWindow('2026-02-30', '2026-09-15', inWindow)).toBe('UNAVAILABLE');
    expect(classifyDeliveryWindow('2026-09-16', '2026-09-15', inWindow)).toBe('UNAVAILABLE');
  });

  it('requires planning action independently of delivery timing', () => {
    expect(assessActionState({ supplyHealth: 'AT_RISK', shortfallKg: 80, riskLabel: 'HIGH', windowPhase: 'BEFORE' }).kind).toBe('required');
  });

  it('keeps unrecognized planning state and invalid quantities incomplete', () => {
    expect(assessActionState({ supplyHealth: 'UNKNOWN', shortfallKg: 0, riskLabel: 'LOW', windowPhase: 'IN_WINDOW' }).kind).toBe('incomplete');
    expect(assessActionState({ supplyHealth: 'COVERED', shortfallKg: Number.NaN, riskLabel: 'LOW', windowPhase: 'IN_WINDOW' }).kind).toBe('incomplete');
    expect(assessActionState({ supplyHealth: 'COVERED', shortfallKg: 0, riskLabel: 'UNASSESSED', windowPhase: 'IN_WINDOW' }).kind).toBe('incomplete');
  });

  it('requires human verification when the window closes without a final physical state', () => {
    expect(assessActionState({ supplyHealth: 'COVERED', shortfallKg: 0, riskLabel: 'LOW', windowPhase: 'OVERDUE' })).toMatchObject({ kind: 'review', title: 'Verify fulfilment after the window' });
    expect(assessActionState({ supplyHealth: 'COVERED', shortfallKg: 0, riskLabel: 'LOW', windowPhase: 'ENDS_TODAY' }).kind).toBe('review');
  });

  it('does not turn an absent schedule into an automatic review or an all-clear', () => {
    const assessment = assessActionState({ supplyHealth: 'COVERED', shortfallKg: 0, riskLabel: 'LOW', windowPhase: 'IN_WINDOW' });
    expect(assessment.kind).toBe('limited');
    expect(assessment.title).toBe('Action status partially assessable');
    expect(assessment.reason).toContain('snapshot timestamp');
    expect(assessment.reason).toContain('not an all-clear');
  });
});