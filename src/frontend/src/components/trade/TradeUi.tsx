'use client';

import { AlertTriangle } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { Breadcrumbs, WorkspaceHeader } from '@/components/WorkspacePrimitives';
import { ApiError } from '@/lib/api';

export function TradePage({ title, eyebrow, description, crumbs, children }: {
  title: string; eyebrow: string; description: string; crumbs: Array<{ label: string; href?: string }>; children: React.ReactNode;
}) {
  return <AppShell programme="Trade coordination"><main className="mx-auto max-w-[1200px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <Breadcrumbs items={crumbs} />
    <WorkspaceHeader eyebrow={eyebrow} title={title} description={description} />
    {children}
  </main></AppShell>;
}

const inputClass = 'mt-1 block min-h-11 w-full rounded-md border border-white/[0.12] bg-background px-3 text-sm outline-none focus:border-primary disabled:opacity-60';

export function Field({ label, name, hint, ...props }: { label: string; name: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <label className="block text-sm"><span className="font-medium">{label}{props.required && <span aria-hidden className="text-warning"> *</span>}</span>
    <input id={name} name={name} className={inputClass} {...props} />
    {hint && <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>}
  </label>;
}

export function TextArea({ label, name, hint, ...props }: { label: string; name: string; hint?: string } & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <label className="block text-sm"><span className="font-medium">{label}{props.required && <span aria-hidden className="text-warning"> *</span>}</span>
    <textarea id={name} name={name} rows={2} className={`${inputClass} py-2`} {...props} />
    {hint && <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>}
  </label>;
}

export function Select({ label, name, options, placeholder, ...props }: {
  label: string; name: string; options: Array<{ value: string; label: string }>; placeholder?: string;
} & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <label className="block text-sm"><span className="font-medium">{label}{props.required && <span aria-hidden className="text-warning"> *</span>}</span>
    <select id={name} name={name} className={inputClass} {...props}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>;
}

export function SubmitButton({ busy, children, variant = 'primary', ...props }: { busy?: boolean; variant?: 'primary' | 'secondary' | 'danger' } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const tone = variant === 'primary' ? 'bg-primary text-primary-foreground' : variant === 'danger' ? 'border border-destructive/60 text-destructive' : 'border border-white/[0.14] text-foreground';
  return <button type="submit" disabled={busy || props.disabled} aria-busy={busy || undefined}
    className={`inline-flex min-h-11 items-center justify-center rounded-md px-4 text-sm font-medium disabled:opacity-60 ${tone}`} {...props}>
    {busy ? 'Saving…' : children}
  </button>;
}

/** Shows the server's message. A 409 is presented as a conflict to resolve, not a generic failure. */
export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const conflict = error instanceof ApiError && error.status === 409;
  const message = error instanceof Error ? error.message : String(error);
  return <div role="alert" className="mt-3 flex gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
    <span>{conflict ? 'Conflict: ' : ''}{message}</span>
  </div>;
}

export function LoadState({ query, empty, children }: {
  query: { isLoading: boolean; error: unknown; data?: unknown }; empty?: React.ReactNode; children: React.ReactNode;
}) {
  if (query.isLoading) return <p className="py-6 text-sm text-muted-foreground" role="status">Loading…</p>;
  if (query.error) return <ErrorNote error={query.error} />;
  if (Array.isArray(query.data) && query.data.length === 0 && empty) return <>{empty}</>;
  return <>{children}</>;
}

export const kg = (value: string | number | null | undefined) =>
  value === null || value === undefined ? '—' : `${Number(value).toLocaleString('en-JM', { maximumFractionDigits: 3 })} kg`;

export const humanize = (value: string) => value.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());

export function Pill({ children, tone = 'neutral', title }: { children: React.ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info'; title?: string }) {
  const tones = { neutral: 'border-white/[0.14] text-muted-foreground', good: 'border-success/50 text-success', warn: 'border-warning/50 text-warning', bad: 'border-destructive/60 text-destructive', info: 'border-primary/50 text-primary' };
  return <span title={title} className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>{children}</span>;
}

export function VerificationPill({ state }: { state: 'DECLARED' | 'VERIFIED' | 'UNSPECIFIED' }) {
  const copy = { DECLARED: ['Declared', 'warn', 'Figures reported by or for the farmer; not independently verified'], VERIFIED: ['Verified', 'good', 'Capacity verified'], UNSPECIFIED: ['Unspecified', 'neutral', 'Recorded before verification status was captured'] } as const;
  const [label, tone, title] = copy[state];
  return <Pill tone={tone} title={title}>{label}</Pill>;
}

/** Supply state of an allocation, keeping proposed, solicited, committed, standby and legacy apart. */
export function SupplyStatePill({ status, consent }: { status: string; consent: string }) {
  if (consent === 'UNSUPPORTED_LEGACY') return <Pill tone="bad" title="Created before supplier consent was recorded; not evidence of agreement">Unsupported legacy</Pill>;
  const map: Record<string, [string, 'neutral' | 'good' | 'warn' | 'bad' | 'info']> = {
    PROPOSED: ['Proposed', 'neutral'], SOLICITED: ['Awaiting supplier', 'info'], COMMITTED: ['Committed', 'good'], STANDBY: ['Authorized standby', 'good'],
    ACTIVATED: ['Activated', 'good'], DECLINED: ['Declined', 'bad'], WITHDRAWN: ['Withdrawn', 'neutral'], LOST: ['Lost', 'bad'],
    RELEASED: ['Released', 'neutral'], CANCELLED: ['Cancelled', 'neutral'], EXPIRED: ['Expired', 'neutral'],
  };
  const [label, tone] = map[status] ?? [humanize(status), 'neutral'];
  return <Pill tone={tone}>{label}</Pill>;
}

export function formValues(form: HTMLFormElement): Record<string, string> {
  const values: Record<string, string> = {};
  new FormData(form).forEach((value, key) => { const text = String(value).trim(); if (text !== '') values[key] = text; });
  return values;
}
