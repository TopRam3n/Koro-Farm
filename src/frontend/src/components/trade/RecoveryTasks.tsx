'use client';

import Link from 'next/link';
import { useState } from 'react';
import {
  type Proposal, type ProposalAction, type RecoveryTask, taskStatusLabel, useApproveProposal, useRecoveryTasks, useRejectProposal,
} from '@/hooks/useRecovery';
import { ErrorNote, Field, LoadState, Pill, SubmitButton, formValues, humanize, kg } from '@/components/trade/TradeUi';

const money = (value: string | null) => value === null ? 'unknown' : `J$${Number(value).toLocaleString('en-JM', { maximumFractionDigits: 2 })}`;
const when = (value: string) => new Date(value).toLocaleString('en-JM', { dateStyle: 'medium', timeStyle: 'short' });

/** Recovery tasks: the agent's proposals awaiting people, what was applied, and why. Refreshes in the background. */
export function RecoveryTasks({ requirementId, empty, showOrder = false }: { requirementId?: string; empty: string; showOrder?: boolean }) {
  const tasks = useRecoveryTasks({ requirementId });
  return <LoadState query={tasks} empty={<p className="mt-3 text-sm text-muted-foreground" role="status">{empty}</p>}>
    <ul className="mt-3 space-y-4" aria-label="Recovery tasks">
      {tasks.data?.map(task => <TaskItem key={task.id} task={task} showOrder={showOrder} timeline={Boolean(requirementId)} />)}
    </ul>
  </LoadState>;
}

function statusTone(status: RecoveryTask['status']) {
  return status === 'COMPLETED' ? 'good' : status === 'AWAITING_APPROVAL' || status === 'ESCALATED' || status === 'FAILED' ? 'warn' : status === 'CANCELLED' ? 'neutral' : 'info';
}

function TaskItem({ task, showOrder, timeline }: { task: RecoveryTask; showOrder: boolean; timeline: boolean }) {
  const proposal = task.current_proposal;
  // While a task is active its latest proposal stays visible, so what was applied is shown next to what is pending.
  const active = !['COMPLETED', 'CANCELLED', 'FAILED'].includes(task.status);
  return <li data-recovery-task={task.status} className="rounded-md border border-white/[0.1] p-4">
    <div className="flex flex-wrap items-center gap-2">
      <Pill tone={statusTone(task.status)}>{taskStatusLabel[task.status]}</Pill>
      {task.status === 'ESCALATED' && Number(task.escalated_kg) > 0 && <span className="text-sm font-semibold">{kg(task.escalated_kg)} needs a coordinator</span>}
      <span className="text-xs text-muted-foreground">Opened {when(task.created_at)}</span>
    </div>
    {showOrder && <Link href={`/orders/${task.requirement_id}`} className="mt-1 inline-block text-xs text-primary underline-offset-2 hover:underline">{task.requirement_label ?? 'Open order'}</Link>}
    {task.terminal_reason && <p className="mt-2 text-sm text-muted-foreground">{task.terminal_reason}</p>}
    {task.status === 'FAILED' && task.last_error && <p role="alert" className="mt-2 text-sm text-destructive">The recovery agent stopped after repeated errors: {task.last_error}</p>}
    {proposal && (active || timeline) && <ProposalCard proposal={proposal} />}
    {timeline && task.steps && task.steps.length > 0 && <Timeline task={task} />}
  </li>;
}

function actionLine(action: ProposalAction) {
  switch (action.type) {
    case 'RELEASE_EXPOSED':
      return `Record that ${action.farmer_name} can no longer supply ${kg(action.quantity_kg)} of their commitment, as their capacity report says`;
    case 'ACTIVATE_STANDBY':
      return `Activate ${kg(action.quantity_kg)} of standby that ${action.farmer_name} (${action.parish}) authorized${action.authorization_valid_until ? ` until ${action.authorization_valid_until}` : ''}`;
    case 'SOLICIT_SUPPLY':
      return `Ask ${action.farmer_name} (${action.parish}) for ${kg(action.quantity_kg)}, reply within ${action.respond_within_hours} hours. Not supply until they accept`;
  }
}

function ProposalCard({ proposal }: { proposal: Proposal }) {
  const [rejecting, setRejecting] = useState(false);
  const approve = useApproveProposal();
  const reject = useRejectProposal();
  const c = proposal.content;
  const pending = proposal.status === 'PENDING';
  const approvals = proposal.approvals.filter(a => a.decision === 'APPROVED');
  const alternatives = c.options.filter(o => o.id !== c.chosen_option_id);

  async function onReject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const ok = await reject.mutateAsync({ proposal, reason: formValues(event.currentTarget).reason ?? '' }).then(() => true, () => false);
    if (ok) setRejecting(false);
  }

  return <section aria-label={`Recovery proposal ${proposal.version}`} data-proposal={proposal.status} className="mt-3 rounded-md border border-primary/30 p-4">
    <div className="flex flex-wrap items-center gap-2">
      <h3 className="text-sm font-semibold">Recovery proposal v{proposal.version}</h3>
      <Pill tone={proposal.status === 'EXECUTED' ? 'good' : proposal.status === 'PENDING' ? 'info' : proposal.status === 'PARTIAL' || proposal.status === 'STALE' ? 'warn' : 'neutral'}>{humanize(proposal.status)}</Pill>
      <Pill tone={proposal.tier === 'ELEVATED' ? 'warn' : 'neutral'} title={c.approval.required}>{proposal.tier === 'ELEVATED' ? 'Needs procurement manager or admin approval' : 'Coordinator approval'}</Pill>
    </div>
    <p className="mt-2 text-xs text-muted-foreground">
      Order needs {kg(c.basis.net_need_kg)}: {kg(c.basis.required_kg)} required, {kg(c.basis.assured_kg)} assured
      {Number(c.basis.exposed_kg) > 0 ? `, ${kg(c.basis.exposed_kg)} no longer backed by reported capacity` : ''}
      {Number(c.basis.in_flight_kg) > 0 ? `, ${kg(c.basis.in_flight_kg)} already requested` : ''}.
    </p>
    <ol className="mt-3 space-y-2 text-sm" aria-label="Proposed actions">
      {c.actions.map((action, index) => {
        const done = proposal.executions.find(e => e.action_index === index);
        return <li key={index} className="border-l-2 border-primary/50 pl-3">
          <span>{actionLine(action)}.</span>
          {done && <span className={`ml-2 text-xs ${done.outcome === 'APPLIED' ? 'text-success' : 'text-destructive'}`}>{done.outcome === 'APPLIED' ? 'Applied' : `Failed: ${String(done.detail.error ?? '')}`}</span>}
          {action.type === 'ACTIVATE_STANDBY' && action.activation_conditions && <span className="block text-xs text-muted-foreground">Supplier&apos;s condition: {action.activation_conditions}</span>}
          {action.type === 'SOLICIT_SUPPLY' && action.message && <blockquote className="mt-1 border-l border-white/[0.15] pl-2 text-xs text-muted-foreground">Request text shown in their farmer portal once approved: &ldquo;{action.message}&rdquo;</blockquote>}
        </li>;
      })}
    </ol>
    {Number(c.escalation_kg) > 0 && <p className="mt-2 text-sm text-warning">{kg(c.escalation_kg)} is not covered by this proposal and is left for a coordinator.</p>}
    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
      <div><dt className="text-muted-foreground">Landed cost change</dt><dd>{c.cost.known
        ? `${Number(c.cost.increase_jmd) > 0 ? '+' : ''}${money(c.cost.increase_jmd)} (${(Number(c.cost.increase_pct) * 100).toFixed(1)}%) against ${money(c.cost.baseline_cost_per_kg_jmd)}/kg now`
        : 'Unknown: some cost inputs are missing'}</dd></div>
      <div><dt className="text-muted-foreground">Why this approval level</dt><dd>{c.approval.reasons.join('; ') || '—'}</dd></div>
      <div><dt className="text-muted-foreground">Decided by</dt><dd>{c.decision.mode === 'model' ? `Recovery agent with ${c.decision.model}` : 'Recovery agent (deterministic rules)'}{c.decision.fallback_reason ? ` (model not used: ${c.decision.fallback_reason})` : ''}</dd></div>
      <div><dt className="text-muted-foreground">Approval valid until</dt><dd>{when(proposal.expires_at)}</dd></div>
    </dl>
    <p className="mt-2 text-sm"><span className="text-xs text-muted-foreground">Reasoning: </span>{c.decision.rationale}</p>
    {c.decision.violations.length > 0 && <p className="mt-1 text-xs text-warning">Checks applied to the model&apos;s answer: {c.decision.violations.join('; ')}</p>}
    {c.decision.information_requests.length > 0 && <p className="mt-1 text-xs text-muted-foreground">The agent suggests finding out: {c.decision.information_requests.join('; ')}</p>}
    {alternatives.length > 0 && <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-muted-foreground">Other options the planner offered ({alternatives.length})</summary>
      <ul className="mt-1 space-y-1">{alternatives.map(o => <li key={o.id}>{o.id}: {o.title}. Standby {kg(o.standby_activated_kg)}, new requests {kg(o.requested_kg)}, left for a coordinator {kg(o.escalation_kg)}.</li>)}</ul>
    </details>}
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-muted-foreground">Draft update for the buyer (not sent)</summary>
      <p className="mt-1">{c.drafts.buyer}</p><p className="mt-1 text-muted-foreground">{c.drafts.status}</p>
    </details>
    {approvals.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Approved by {approvals.map(a => `${a.reviewer_name ?? 'a reviewer'} (${humanize(a.reviewer_role)})`).join(', ')}.</p>}
    {proposal.status_reason && <p className="mt-2 text-xs text-muted-foreground">{proposal.status_reason}</p>}
    {pending && proposal.viewer.can_approve && <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" disabled={approve.isPending} onClick={() => approve.mutate({ proposal })} className="min-h-11 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
        {approve.isPending ? 'Approving…' : 'Approve proposal'}
      </button>
      <button type="button" onClick={() => setRejecting(v => !v)} className="min-h-11 rounded-md border border-white/[0.14] px-4 text-sm">Reject proposal</button>
    </div>}
    {pending && proposal.viewer.already_decided && <p className="mt-3 text-xs text-muted-foreground">You have approved this proposal. {proposal.tier === 'ELEVATED' ? 'It also needs a procurement manager or organization administrator.' : ''}</p>}
    {pending && !proposal.viewer.can_approve && !proposal.viewer.already_decided && <p className="mt-3 text-xs text-muted-foreground">Your role cannot approve recovery proposals.</p>}
    <p className="mt-2 text-xs text-muted-foreground">Approving applies exactly what is shown. The system re-checks stock, supplier authorizations and approvals before acting, and refuses anything that has changed.</p>
    {rejecting && <form onSubmit={onReject} aria-label="Reject proposal" className="mt-3 flex flex-wrap items-end gap-2">
      <div className="min-w-[240px] flex-1"><Field label="Reason for rejecting" name="reason" required minLength={3} hint="The agent will not propose the same suppliers again for this task." /></div>
      <SubmitButton busy={reject.isPending} variant="secondary">Reject</SubmitButton>
    </form>}
    <ErrorNote error={approve.error ?? reject.error} />
  </section>;
}

function Timeline({ task }: { task: RecoveryTask }) {
  return <details className="mt-3" open>
    <summary className="cursor-pointer text-sm font-medium">Recovery timeline</summary>
    <ol className="mt-2 space-y-1 text-xs" aria-label="Recovery timeline">
      {task.steps?.map(step => <li key={step.sequence} className="flex flex-wrap gap-x-2 border-l border-white/[0.12] pl-3">
        <span className="font-medium">{humanize(step.kind)}</span>
        <span>{step.summary}</span>
        <span className="text-muted-foreground">{when(step.created_at)} · {step.actor_name}</span>
      </li>)}
    </ol>
  </details>;
}
