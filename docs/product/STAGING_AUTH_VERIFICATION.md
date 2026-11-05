# Staging verification: real Supabase authentication

**Status: not yet run.** This verification must pass before any public deployment of R1.

R1's browser E2E runs against a test-only auth stand-in (`src/frontend/e2e/r1/support/auth-stub.mjs`). The
stand-in proves the app and API enforce memberships and organization boundaries for a bearer token. It does not
prove that a hosted Supabase project issues, refreshes and revokes those tokens the way the app assumes. This task
covers that gap against a staging deployment.

## What it checks

| # | Check | Pass condition |
| --- | --- | --- |
| 1 | Wrong password | Stays on `/login`; no session is stored in the browser |
| 2 | Sign-in | The stored access token's issuer is the staging Supabase project; `GET /me` returns 200 with the user's organization |
| 3 | Session handling | Survives a reload and a new tab; the refresh-token grant returns a new access token that the API accepts |
| 4 | Cross-organization access | A same-organization colleague can read the order (control). A user from another organization sees "requirement not found" in the UI, gets 404 from the API, and gets 403 or 404 when sending organization A's id in `X-Organization-ID` |
| 5 | Sign-out | Returns to `/login`; the stored session is cleared; protected pages redirect to `/login`; the access token issued before sign-out is refused by the API with 401 |

Check 5 no longer depends on Supabase rejecting the token at `GET /auth/v1/user`. In staging the API verifies the
token against the project's signing keys, then requires the token's `auth.sessions` row, which Supabase deletes on
sign-out (`src/backend/app/core/auth.py`; infrastructure plan §8b). PostgreSQL tests prove the API refuses the token
once the row is gone (`tests/test_session_auth.py`). This check proves that real Supabase deletes the row and the
deployed API refuses the token. It remains the release gate: if it fails, do not deploy.

## Prerequisites

1. A staging Supabase project (https, hosted; the spec refuses `localhost`), with email/password sign-in enabled.
2. The staging API deployed with `APP_ENV=staging`, `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` for that project,
   `ALLOW_INSECURE_DEMO_AUTH` and `AUTH_SESSION_VERIFICATION` unset (staging always checks sessions in the database),
   and the supply-exception worker running. The project signs tokens with an asymmetric key (setup guide §1.4).
3. The staging frontend built with `NEXT_PUBLIC_APP_MODE=live` and the same Supabase project.
4. Three Supabase users (created in the Supabase dashboard; [R1_PRODUCT_OWNER_SETUP_GUIDE.md](R1_PRODUCT_OWNER_SETUP_GUIDE.md)
   §1.5), each given an active KoroFarm membership with `python -m src.backend.scripts.provision_staging <plan.json>
   --apply` (§1.6, §1.9):
   - `coordinator_a`: supply coordinator in organization A;
   - `colleague_a`: any staff role in organization A;
   - `coordinator_b`: supply coordinator in organization B.
5. One order (requirement) created in organization A: sign in as `coordinator_a` and create it in **Orders**. That
   also exercises the real app. Its id (from the order page's address) goes in `STAGING_ORG_A_ORDER_ID`.
6. `python -m src.backend.scripts.check_staging --api-url … --frontend-origin …` passes. It is the configuration,
   database, Data API, session store, signing keys, health, worker and CORS check, and it is not a substitute for this
   test.

## Run

Keep the users file outside the repository; it holds real passwords.

```json
{
  "coordinator_a": { "email": "...", "password": "...", "organization_id": "<org A uuid>" },
  "colleague_a":   { "email": "...", "password": "...", "organization_id": "<org A uuid>" },
  "coordinator_b": { "email": "...", "password": "...", "organization_id": "<org B uuid>" }
}
```

```bash
cd src/frontend
STAGING_BASE_URL=https://<staging frontend> \
STAGING_API_URL=https://<staging api> \
STAGING_SUPABASE_URL=https://<project-ref>.supabase.co \
STAGING_SUPABASE_PUBLISHABLE_KEY=<publishable key> \
STAGING_USERS=/path/outside/repo/staging-users.json \
STAGING_ORG_A_ORDER_ID=<uuid> \
npm run test:staging-auth
```

Without all six variables the spec is skipped, which is why it does not run in CI. A skipped run is not a pass.

## Recording the result

Record in the release notes: the date, the frontend and API commit, the Supabase project ref, the Playwright output
(5 passed) and the screenshots in `src/frontend/artifacts/staging-auth/`. Change the status line above only when
all five checks have passed against the build being released.
