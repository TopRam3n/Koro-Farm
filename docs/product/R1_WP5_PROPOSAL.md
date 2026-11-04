# R1 — WP5 scope proposal (for review; no implementation started)

> **Update, 3 November 2026: priority instruction.** The staging baseline comes first
> ([R1_INFRASTRUCTURE_PLAN.md](R1_INFRASTRUCTURE_PLAN.md)).
> - Planning priority: **M1** (role-aware workspace), **M2** (buyer portal) and **M3** (external notifications and
>   supplier consent; it builds on the outbound pattern in the infrastructure plan §10).
> - **M4–M7 are deferred** until the staging baseline is established, unless a demonstrated pilot dependency requires
>   them.
> - No WP5 feature implementation is authorized.

**Basis:**
- WP4 accepted as engineering-complete ([R1_WP4_DECISIONS.md](R1_WP4_DECISIONS.md)).
- The deferred items in [TECH_DEBT_REGISTER.md](TECH_DEBT_REGISTER.md).
- The open items in [R1_PILOT_READINESS_CHECKLIST.md](R1_PILOT_READINESS_CHECKLIST.md).

**Theme:** make the pilot workable day to day for every role. The safety rules from WP1–WP4 stay unchanged:
- consent;
- approval;
- the stock ledger;
- truthful status;
- tenant isolation.

**Guiding rule:** nothing in WP5 relaxes a WP1–WP4 safeguard. Where a milestone touches one, it is called out with the existing test that must keep passing.

## 1. Pilot-readiness work that is not WP5

The checklist blockers are operational and run in parallel, outside WP5:
- Supabase staging authentication;
- merges;
- worker supervision;
- backup;
- release-audit review.

WP5 must not delay them, and they do not need WP5 code. Engineering support for them (running the staging authentication checklist, helping with the dry run) is time-boxed alongside WP5.

## 2. Proposed milestones

### M1. Role-aware order workspace (debt items 20 and 18, part)
- **Problem:** warehouse operators, buyers and auditors see one order page built for coordinators. Panels they may not use show the server's refusals.
- **Scope:**
  - one order workspace whose sections follow the viewer's permissions: warehouse (receive, grade, ship, deliver), coordinator (everything), procurement manager (approvals, variance), auditor (read and flag);
  - a consolidated fulfilment view across orders (today's receipts, open shipments, deliveries awaiting confirmation, flagged event times, open disputes), replacing the read-only *Fulfilment Center* summary.
- **Acceptance criteria:**
  - no panel shows a refusal for an action the role cannot take;
  - every action is still enforced by the server;
  - the browser test covers each role.

### M2. Buyer portal (debt item 6 follow-up)
- **Scope:**
  - order status and delivery history for the buyer's own orders, with confirmed, delivered, disputed and outstanding quantities shown separately;
  - dispute follow-up (the resolution is visible to the buyer);
  - downloadable delivery confirmation records.
- **Acceptance criteria:**
  - a buyer sees only their own buyer record's orders, across sessions and organizations;
  - a staff relay is still labelled as a relay;
  - tenancy tests are extended.

### M3. Supplier notifications outside the app (debt item 4)
- **Decision needed first:**
  - which channel (SMS, WhatsApp or email) and which provider;
  - the farmers' consent to be contacted;
  - message templates.
- **Scope:** an outbound notification service for requests, reminders, deadlines and release agreements. Every send is recorded with its delivery status. Agent drafts are never sent without the existing approval.
- **Acceptance criteria:**
  - no message is sent without recorded consent to contact;
  - a failed send is visible;
  - nothing is sent from production until separately authorized.

### M4. Planning beyond grade A, and organization policies (debt items 3, 5, 18)
- **Scope:**
  - grades B and C in planning and recovery eligibility, with no substitution between grades unless an order explicitly allows it;
  - organization-level defaults for reply windows (today 24 h, 4 h and 48 h are code constants).
- **Acceptance criteria:**
  - the existing grade and eligibility tests still pass;
  - P7's "no silent substitution" holds;
  - policy changes are versioned and audited like the approval policy.

### M5. Per-crop harvest re-verification (debt item 17; WP4 decision 3)
- **Scope:** a per-crop re-verification period with the 7-day default.
- **Acceptance criteria:**
  - a period can differ from 7 days only with a recorded basis: documented crop handling requirements or verified pilot evidence;
  - it never becomes an expiry;
  - changes are audited.

### M6. Physical event times, second step (debt item 27)
- **Scope:**
  - a stated grading time beside the system time;
  - a physical time on delivery corrections;
  - the sequence checks extended to grading.
- **Acceptance criteria:**
  - legacy rows are labelled, not rewritten;
  - flags still block close-out until reviewed.

### M7. Clean-up (debt items 12, 13, 19)
- Delete or rewrite the pre-R1 demo scripts.
- Retire or relabel the rule-based "agent evaluation".
- Remove the 410 availability stub one release after R1.

## 3. Deferred beyond WP5 unless the pilot shows a need

- Re-planning released stock automatically (item 25): released stock currently waits for re-verification by design.
- Reserving stock when a supplier is asked (item 10).
- Supply assurance for marketplace orders (item 2). This is needed only before marketplace orders are re-enabled, which needs its own decision.

## 4. Decisions needed before implementation

1. Which milestones are in WP5, and in what order. **Current priority (3 November 2026):** M1, M2, M3. M3 needs its channel decision first. M4–M7 wait for the staging baseline.
2. M3: channel, provider, consent wording, and whether WP5 sends anything from staging.
3. M4: whether any order may accept another grade, and who decides.
4. M5: the evidence standard for a per-crop period.

## 5. Unchanged release gates

- Supabase staging authentication.
- Worker supervision.
- Real-model validation: production inference stays disabled.
- Merges and deployment need separate authorization.
