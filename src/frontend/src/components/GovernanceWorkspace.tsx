'use client';

import { ShieldCheck } from 'lucide-react';
import { AppShell } from '@/components/AppShell';

const copy = {
  users: ['Users & Access', 'Invite-only membership, role assignment, deactivation, and organization-scoped access are enforced by the backend.'],
  organization: ['Organization', 'The active organization comes from an authenticated membership and explicit organization context.'],
  policies: ['Approval Policies', 'Recovery proposal, approval, and execution thresholds must be configured before governed automation is enabled.'],
} as const;

export function GovernanceWorkspace({ kind }: { kind: keyof typeof copy }) {
  const [title, description] = copy[kind];
  return <AppShell><main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><p className="section-eyebrow">Administration</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em]">{title}</h1><p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p><section className="operational-panel mt-7 p-6"><ShieldCheck className="h-5 w-5 text-primary" /><h2 className="mt-3 text-lg font-semibold">Governed live session required</h2><p className="mt-2 text-sm text-muted-foreground">This workspace does not fabricate users, memberships, or policies in offline demo mode. Connect the authenticated organization API to administer authoritative records.</p></section></main></AppShell>;
}
