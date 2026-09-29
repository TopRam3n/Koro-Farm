'use client';

import { ShieldCheck } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { DataTrustIndicator } from '@/components/DataTrustIndicator';
import { Breadcrumbs, WorkspaceHeader } from '@/components/WorkspacePrimitives';

const copy = {
  users: ['Users & Access', 'Invite-only membership, role assignment, deactivation, and organization-scoped access are enforced by the backend.'],
  organization: ['Organization', 'The active organization comes from an authenticated membership and explicit organization context.'],
  policies: ['Approval Policies', 'Recovery proposal, approval, and execution thresholds must be configured before governed automation is enabled.'],
} as const;

export function GovernanceWorkspace({ kind }: { kind: keyof typeof copy }) {
  const [title, description] = copy[kind];
  return <AppShell><main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><Breadcrumbs items={[{ label: 'Command Center', href: '/' }, { label: title }]} /><WorkspaceHeader eyebrow="Administration" title={title} description={description} trust={<DataTrustIndicator state="UNVERIFIED" detail="Authoritative organization records require a governed live session" />} /><section className="operational-panel max-w-3xl p-5 sm:p-6" aria-labelledby="governance-required-title"><ShieldCheck className="h-5 w-5 text-primary" /><h2 id="governance-required-title" className="mt-3 text-lg font-semibold">Governed live session required</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">This workspace does not fabricate users, memberships, or policies in offline demo mode. Connect the authenticated organization API to administer authoritative records.</p></section></main></AppShell>;
}
