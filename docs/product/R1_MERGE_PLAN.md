# R1 review and merge plan

**Status:** prepared for review. **No merge is authorized.**
- Every merge needs the product owner's explicit go-ahead.
- Nothing merges automatically.
- No deployment follows a merge.

## Branch stack (checked 6 November 2026; all pushed, local equals remote)

Strictly linear: each branch contains the one before it, and `main` has not moved since WP1 branched.

| # | Branch | Tip | New commits | Change vs previous | Files deleted | Last CI |
|---|---|---|---|---|---|---|
| 0 | `main` | `731c459` | | pre-R1 code (public repository) | | |
| 1 | `feat/r1-trade-core` (WP1) | `68d1767` | 18 | 126 files, +6202 / −867 | 7 (below) | green at handoff |
| 2 | `feat/r1-wp2-supply-exceptions` | `6edff96` | 5 | 60 files, +3480 / −67 | 0 | green at handoff |
| 3 | `feat/r1-wp3-agent-orchestration` | `4401294` | 2 | 64 files, +4391 / −350 | 0 | green at handoff |
| 4 | `feat/r1-wp3-model-providers` | `8519a3a` | 3 | 25 files, +2285 / −363 | 0 | green at handoff |
| 5 | `feat/r1-wp4-fulfilment-accounting` | `267ac9c` | 6 | 84 files, +6332 / −462 | 0 | 41671496065 (WP4); later follow-up green |
| 6 | `feat/r1-staging-infrastructure` | `07400f0` | 5 | 39 files, +3988 / −57 | 0 | 41950961171 |
| 7 | `feat/r1-wp5` | `28c2fda` (code); later commits are records only | 5 | about 100 files | 0 | 42168476863 |

**Whole stack against `main`:** 228 files added, 75 modified, 7 deleted.

**The only deletions** are in WP1 commit `4d27035`, "retire the offline demo replay":
- `src/frontend/src/lib/demoApi.ts`
- `src/frontend/src/components/DemoControls.tsx`
- `src/frontend/e2e/competition.spec.ts`
- `src/frontend/e2e/enterprise.spec.ts`
- `src/frontend/playwright.config.ts` (replaced by `playwright.r1.config.ts`)
- `src/frontend/src/test/competition.test.tsx`
- `src/frontend/src/test/demoRoles.test.ts`

These were intentional and recorded in `R1_WP1_HANDOFF.md`, `R1_WP1_REPORT.md` and `R1_WP1_VERIFICATION.md`. The demo
replay mirrored a flow without supplier consent, so keeping it would have shown behaviour the product no longer has.
No later branch deletes a file.

## Merge dependencies

1. **Order is fixed.** Each branch depends on all earlier ones: shared migrations 0001–0030 in sequence, the
   authorization model, the outbox and the fulfilment records. Merge 1 → 7 in order.
2. **Migrations** form a single linear Alembic chain (one head after each branch). No branch rewrites an earlier
   migration.
3. **WP5 depends on staging infrastructure:**
   - the session check, the Data API checks and the `with_env` tooling;
   - CI's `container-images` job, which exists from branch 6 onward.

   Branches 1–5 run only the `verify` job.

## Recommended procedure

**Approach:** one pull request per work package, merged in order, each into `main` after the previous one.
- Each pull request then shows only that package's change.
- Use merge commits, not squash, to keep the reviewed commits and their CI history.
- Because the stack is linear, each merge is effectively a fast-forward of reviewed commits. No conflict is expected
  while `main` stays untouched.

**For each pull request:**
1. Open it from the branch into `main`. The description is in the template below.
2. Required checks: `verify` (backend on PostgreSQL, frontend lint, typecheck and unit tests, production build and
   bundle check, R1 browser E2E), plus `container-images` from branch 6 onward. All green on the pull request's
   merge commit.
3. Review against the package's handoff: scope, safeguards, tests, and the deletions list above (WP1 only).
4. Product owner: explicit approval.
5. Merge, then confirm CI on `main` before opening the next pull request.

**Alternative, if the product owner prefers one review:** a single pull request from `feat/r1-wp5` into `main`. Same
checks; 300+ files, so harder to review.

**After the last merge:**
- tag `r1-rc1` (no release or deployment);
- keep the feature branches until the pilot decision, and do not delete them automatically;
- continue with `AFTER_WP5_INTEGRATION_CHECKLIST.md`.

## Pull request description template

```
R1 <WP>: <title>

Scope: <one paragraph from the package's handoff>
Handoff: docs/product/R1_<WP>_HANDOFF.md
Safeguards unchanged or strengthened: consent, approval, stock ledger, truthful status, tenant isolation
Migrations: <range>; one Alembic head; tested on PostgreSQL 17
Files deleted: none (WP1: the 7 demo-replay files listed in R1_MERGE_PLAN.md)
Checks: verify [+ container-images] green on <commit>
Not included: deployment, external services, live data
Merge: product owner approval required; merge commit, no squash
```

## Diff review notes for WP5

- **Removals:** none.
- **Intentional behaviour changes:**
  - planning requires `supply.manage`;
  - buyers' home page is `/buyer`;
  - the Fulfilment Center shows the queue view;
  - the coordinator is not offered the variance close;
  - forecast evidence needs lineage and an explicit rights decision.
- **Unrelated changes:** none. Untracked local files (demo videos, `brag-output`, `tmp/`, local artifacts, agent
  configuration) are not part of any branch and must not be added.
