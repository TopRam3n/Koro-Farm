# R1 browser E2E

Runs the R1 order workflow through the real UI against a live stack:

- production Next.js build (live mode, no demo replay);
- FastAPI backend with real membership-based authorization (`APP_ENV=test`, demo auth bypass **off**);
- a disposable PostgreSQL database migrated with Alembic;
- the deterministic supply-exception worker (`python -m src.backend.app.worker`), which turns outbox events
  into supply exceptions and runs the reply-deadline and standby-expiry timers;
- `support/auth-stub.mjs`, a **test-only** stand-in for the Supabase Auth endpoints the app calls
  (password sign-in, token refresh, `GET /auth/v1/user`, logout). The login page and the backend's token
  check run unchanged; they point at the stand-in instead of a hosted Supabase project.

The specs create every buyer, supplier, lot and order through the UI with run-unique names. The seed
creates two organizations, six users, one supplier record and one buyer record: the farmer account (`farmer_a`)
must be linked to the supplier it reports for, and the buyer account (`buyer_a`) to the buyer it confirms for.
`warehouse_a` is a warehouse operator.

| Spec | Covers |
| --- | --- |
| `order-workflow.spec.ts` | order creation, versioned edits, proposed → awaiting supplier → committed, second session, other organization |
| `consent-and-boundaries.spec.ts` | decline and withdrawal, refused cancellation, cross-organization tokens, independent sessions |
| `capacity-exceptions.spec.ts` (WP2) | `/health/worker` reports the running worker as operational and `/system/status` refuses an anonymous request; the header shows the real monitoring status; the farmer sees the request and its reply deadline in the portal and accepts it there (farmer navigation only); the farmer reports less in the portal; the coordinator's already-open order page shows the exposure and an open exception without a reload; acknowledge; manual resolve refused while exposed; restored capacity closes the exception by itself; other organization sees nothing. **Needs the worker running.** |
| `recovery-approval.spec.ts` (WP3) | Supply is committed with authorized standby through recorded supplier decisions. A relayed capacity cut makes the worker's recovery agent propose: release 110 kg, activate 60 kg of standby, ask a supplier for 50 kg. Nothing changes until approval; another organization sees nothing. The coordinator approves the exact proposal; the gateway applies all three actions; the exception closes. The new supplier's recorded acceptance completes recovery; the timeline shows the agent, the approver and the gateway. **Needs the worker running.** |
| `fulfilment-reconciliation.spec.ts` (WP4) | The spec section 6 story in independent sessions: 730 kg committed through the supplier's recorded decision; a fulfilment site added; the warehouse operator records 725 kg received, grades 705 kg accepted and 20 kg rejected, ships, dispatches and records 705 kg delivered; the buyer confirms 705 kg in their own account (no more than delivered); the coordinator reconciles and the order shows "Reconciled, not closed" with the blockers, never 730 kg delivered or completed; the coordinator cannot accept the variance; a procurement manager closes it with a documented reason; after reload and in a new session it stays "Closed with variance", with 5 kg released; another organization sees nothing. Plantain is used so no other spec's stock is planned. |
| `workspaces.spec.ts` | route map, command palette, Scenario Lab is visibly non-persistent |

## Procedure (CI runs the same steps: `.github/workflows/competition-readiness.yml`)

From the repository root, with a disposable PostgreSQL server (see `src/backend/.env.test.local`, not committed):

```bash
# 1. Fresh database, migrations, two test organizations and users
createdb -h 127.0.0.1 -p 55499 -U kf_r1_test korofarm_r1_disposable_e2e
export APP_ENV=test
export DATABASE_URL=postgresql+psycopg://kf_r1_test:<password>@127.0.0.1:55499/korofarm_r1_disposable_e2e
(cd src/backend && ../../.venv/Scripts/python.exe -m alembic upgrade head)
.venv/Scripts/python.exe -m src.backend.scripts.seed_e2e /path/outside/repo/users.json

# 2. Auth stand-in and API
KOROFARM_E2E_AUTH_STANDIN=1 node src/frontend/e2e/r1/support/auth-stub.mjs /path/outside/repo/users.json 54999 &
SUPABASE_URL=http://127.0.0.1:54999 SUPABASE_PUBLISHABLE_KEY=e2e-test-key APP_ENV=test \
  ALLOW_INSECURE_DEMO_AUTH=false CORS_ORIGINS=http://127.0.0.1:3100 \
  .venv/Scripts/python.exe -m uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8100 &
SUPABASE_URL=http://127.0.0.1:54999 SUPABASE_PUBLISHABLE_KEY=e2e-test-key APP_ENV=test   WORKER_POLL_SECONDS=1 .venv/Scripts/python.exe -m src.backend.app.worker &

# 3. Frontend (production build, live mode)
cd src/frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54999 \
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=e2e-test-key NEXT_PUBLIC_APP_MODE=live npx next build
npx next start -p 3100 -H 127.0.0.1 &

# 4. Tests
R1_E2E_USERS=/path/outside/repo/users.json npm run test:e2e
```

Real Supabase sign-in, session handling, cross-organization access and sign-out are **not** covered here;
they are a separate release gate: `docs/product/STAGING_AUTH_VERIFICATION.md`.

## Safety boundaries

- The stand-in refuses to start unless `KOROFARM_E2E_AUTH_STANDIN=1` is set, and it also refuses when
  `NODE_ENV=production` or `APP_ENV` is set to anything other than `test`. It listens on 127.0.0.1 only.
- The backend requires `APP_ENV` to be `development`, `test`, `staging` or `production` (missing or other values
  stop startup), and in `staging`/`production` refuses to start unless
  `SUPABASE_URL` is an https URL on a public host, so a local stand-in cannot back a production API
  (`src/backend/app/core/config.py`, tests in `src/backend/tests/test_runtime_security.py`).
- No application code imports the stand-in. `npm run check:bundle` fails if a production build contains it.

The users file holds generated test passwords; keep it outside the repository. Screenshots are written to
`artifacts/r1-e2e-screens/` (copies of one run are in `docs/product/evidence/wp1/`).
