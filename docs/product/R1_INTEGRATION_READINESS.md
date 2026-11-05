# R1 — Integration readiness

**Updated:** 4 November 2026 (security review amendments), branch `feat/r1-staging-infrastructure`.

**Statuses:**

| Status | Meaning |
|---|---|
| NOT STARTED | No work yet |
| PREPARED | Code and configuration ready; tested locally or in CI |
| AWAITING PRODUCT OWNER | Needs an account, setting or decision from you |
| CONNECTED | Talked to the real external service |
| VERIFIED | Its acceptance checks passed against the real service |
| BLOCKED | Cannot proceed |

**Rule:** code-level tests prove behaviour, not connectivity. Nothing below is CONNECTED or VERIFIED unless the evidence is a run against the real service. As of today, **the only external service KoroFarm has actually run against is GitHub Actions**.

## Summary

| # | Integration | Status | Next action |
|---|---|---|---|
| 0 | Existing pilot database | AWAITING PRODUCT OWNER | Confirm whether one exists (guide, step 0) |
| 1 | Supabase project (staging) | AWAITING PRODUCT OWNER | Create the project (guide §1) |
| 2 | Supabase PostgreSQL connection | PREPARED | Your connection string in a local gitignored file; run `check_staging` |
| 3 | Alembic migrations on Supabase | PREPARED | Run after item 2, with your go-ahead |
| 4 | Data API lockdown | PREPARED | Migrations 0026 and 0027, switching the Data API off (guide §1.3), three-proof verification (guide §1.11) |
| 5 | Supabase Auth: sign-in, refresh, sign-out (immediate revocation) | PREPARED | Asymmetric signing key and users (guide §1.4, §1.5) |
| 6 | Staging provisioning (organizations, memberships) | PREPARED | Plan file with the user ids (guide §1.6) |
| 7 | Cross-tenant verification on staging | PREPARED | `npm run test:staging-auth` after deployment |
| 8 | Backup and restore | PREPARED | Rehearse against Supabase once it exists |
| 9 | Hosting: VPS | AWAITING PRODUCT OWNER | VPS specifications (plan §3) |
| 10 | Container images | PREPARED | CI job `container-images` (see evidence) |
| 11 | HTTPS and routing (Caddy) | PREPARED | Domain and DNS (guide §2) |
| 12 | Worker supervision | PREPARED | Proven in CI; on the real host after deployment |
| 13 | Uptime monitoring of `/health/worker` | AWAITING PRODUCT OWNER | Monitor account and alert recipient (guide §3) |
| 14 | Logging and alerting | PREPARED (logs) / NOT STARTED (central alerting) | Uptime alert first |
| 15 | Secrets handling | PREPARED | Password manager plus server env file |
| 16 | MiniMax (synthetic evaluation) | AWAITING PRODUCT OWNER | Key in a local file; review the terms (guide §4) |
| 17 | Nebius Token Factory (synthetic evaluation) | AWAITING PRODUCT OWNER | Key in a local file; turn on Zero Data Retention (guide §5) |
| 18 | Anthropic adapter | NOT STARTED | Present and disabled; no decision requested |
| 19 | Email delivery for Auth (SMTP) | NOT STARTED | Only if email sign-up or reset is needed at scale |
| 20 | External messaging: SMS, WhatsApp, email (WP5 M3) | NOT STARTED | Channel decision (WP5) |
| 21 | Agricultural data sources, government, institutional partners | NOT STARTED | Ingestion API is the foundation (plan §10) |
| 22 | GitHub Actions CI | VERIFIED | Runs on every push |

## Details and evidence

### 0. Existing pilot database: AWAITING PRODUCT OWNER

**Found on this workstation:**
- no connection to any database other than local development and the disposable test instance;
- no hosting configuration;
- no Supabase project settings. The frontend's local settings point at local demo stand-ins.

WP4's "pilot database not reachable" was an assumption.

- **Plan:** staging starts as a new, empty database, with no historical migration or release audit.
- **If a database with real records exists:** tell me where it lives, without sending credentials. The backup and read-only dry run from the WP4 decisions then apply, and `--apply` stays unauthorized.

### 1. Supabase project (staging): AWAITING PRODUCT OWNER

Creating a project is an account action that may incur cost (Pro plan). Instructions: guide §1.

### 2. Supabase PostgreSQL connection: PREPARED

**Prepared:**
- **Staging and production refuse to start unless the URL is explicit, avoids the development credentials, and requires TLS for a remote host:** `app/core/config.py`.
- **Transaction pooler (port 6543):** prepared statements off.
- **Pool, timeout and `application_name` settings:** `app/infrastructure/database/session.py`.
- **Alembic URL escaping:** `alembic/env.py`.

**Evidence (local):**
- `test_runtime_security.py`: 24 new database and model-approval cases.
- `test_staging_readiness.py`: engine options.
- `test_alembic_accepts_url_encoded_passwords`: on PostgreSQL 17. It fails without the fix ("invalid interpolation syntax"), which I confirmed.

**Not yet:** any connection to Supabase.

### 3. Alembic migrations on Supabase: PREPARED

- **Evidence:** the full chain 0001–0026 runs on fresh PostgreSQL 17 in CI and locally (`test_migrations_postgres.py`).
- **Not yet:** run on Supabase. The first run is on an empty project; record its output.

### 4. Data API lockdown: PREPARED

**Prepared:**
- migrations `0026_supabase_data_api_lockdown` and `0027_supabase_data_api_hardening`;
- `app/infrastructure/database/data_api.py`, for findings and re-apply statements;
- `scripts/data_api_lockdown.py`;
- `check_staging`'s `data_api_grants` and `data_api_http` checks.

**Security review amendment (4 November 2026):** both checks were corrected (infrastructure plan §8a).
- **`data_api_http` could report PASS on an authentication failure.** It sent the publishable key as a bearer token and accepted any 401.
  - **Now:** the key goes only in `apikey`, and a control request must prove Supabase accepts it.
  - PASS requires Supabase's disabled-Data-API signature. Permission denied, not served, authentication failure and unrecognized answers all FAIL.
- **The grant audit missed several paths:**
  - `PUBLIC` function execution, column grants and grants through role membership;
  - other owners' default privileges, and future objects.
  - **Now:** it evaluates effective privileges, reads every relevant owner's default privileges, and runs a rolled-back probe. If the probe cannot run, the check FAILs.

**Evidence (PostgreSQL 17, Supabase roles and default grants simulated):**
- `test_functions_executable_through_public_are_caught_and_closed_by_0027`:
  - at 0026, a function executable through `PUBLIC` is caught three ways: existing grant, built-in default and probe;
  - after 0027: clean, and later functions get no `PUBLIC` grant.
- `test_column_grants_and_grants_through_role_membership_are_effective_privileges`.
- `test_default_privileges_for_new_objects_are_caught_by_the_catalog_and_the_probe`: covers a default grant reaching `anon` through membership, and another owner's default privileges, which the lockdown cannot remove and which stay FAIL.
- `test_the_probe_leaves_nothing_behind_and_unverifiable_new_objects_fail`.
- HTTP classification: `test_data_api_probe_*` in `test_staging_readiness.py`, 11 cases; no Authorization header is sent.

**Evidence (local PostgreSQL 17, with Supabase's roles and default grants simulated):**
- **Before 0026:** `anon` can reach `supply_allocations` and other tables.
- **After 0026:**
  - no privilege for anon, authenticated or service_role;
  - every table has RLS;
  - the owner still reads rows;
  - a table created later gets no grant.
- **Re-apply after a simulated restore** removes grants that came back, leaving rows untouched.

**Not yet:**
- run on Supabase;
- the HTTP probe against the real REST endpoint. Supabase's disabled signature comes from its documentation and has not been observed yet;
- the dashboard switch (guide §1.3).

### 5. Supabase Auth: PREPARED

**Security review amendment (4 November 2026):** staging and production no longer rely on `GET /auth/v1/user`.
- **Token:** verified locally against the project's published ES256/RS256 keys, checking issuer, audience, role, expiry, `sub` and `session_id`.
- **Session:** the `auth.sessions` row must exist for that session and user, must not be past `not_after`, and the user must not be deleted or banned. Supabase deletes the row on sign-out.
- **Outcomes:**
  - invalid, expired or signed-out tokens get 401;
  - unreadable keys or session records get 503;
  - membership authorization is unchanged, so a non-member gets 403.
- **Startup:** staging and production refuse `AUTH_SESSION_VERIFICATION=remote`.
- Design: infrastructure plan §8b.

**Evidence:**
- `tests/test_session_auth.py`:
  - 12 token and configuration tests: expiry, issuer, audience, role, missing session, forged, HS256, `none` and RSA downgrades, key caching, rotation and outage;
  - on PostgreSQL with a simulated `auth` schema, through the real `/me` route:
    - active session accepted;
    - local sign-out refuses that token immediately while another device's session continues;
    - global sign-out refuses all;
    - expired token, session past `not_after`, banned or deleted user, missing session, borrowed session, forged token: 401;
    - non-member and other organization: 403;
    - unreadable session table or keys: 503.
- CI checks the image refuses `remote` in staging and answers a malformed token with 401.
- **These prove the API's behaviour, not Supabase's.**

**Prepared (unchanged):**
- the staging authentication spec covers wrong password, sign-in, refresh, cross-organization access and sign-out (`e2e/staging/auth.spec.ts`, `STAGING_AUTH_VERIFICATION.md`);
- `check_staging`'s `auth_settings` check covers email sign-in, open sign-up and confirmation.

**Evidence:** the R1 browser suite (27 tests) passes against the test-only stand-in, which proves the app's enforcement, not Supabase's behaviour.

**Not yet:** any run against Supabase.
- `src/frontend/artifacts/staging-auth-results/` is from a run without the staging variables. Every test was skipped, which is **not a pass**.

**Answered in code:** the API now checks sessions locally, so check 5 no longer depends on `/auth/v1/user`. Check 5 stays the release gate. It proves against the real project that sign-out deletes the session row and that the deployed API refuses the old token.

**Also unproven until the first real check:** whether the `postgres` role can read `auth.sessions` and `auth.users`. `check_staging`'s `auth_session_store` answers it.

### 6. Staging provisioning: PREPARED

`scripts/provision_staging.py`:
- dry run by default;
- additive and idempotent;
- reports conflicts and writes nothing when there are any;
- staff roles only, with no passwords;
- refuses production.

**Evidence:** `test_staging_readiness.py`, on SQLite and PostgreSQL:
- dry run versus apply;
- idempotent re-run;
- email conflict;
- existing membership with a different role;
- refused plans;
- provisioned accounts reach only their own organization through the real authorization path.

### 7. Cross-tenant verification on staging: PREPARED

Spec in place. It needs items 1, 5, 6 and a deployed stack (items 9–11).

### 8. Backup and restore: PREPARED

**Evidence:** rehearsed on 3 November 2026 on the local disposable PostgreSQL 17 instance (plan §6):
- the restored copy matched the source: Alembic revision, row counts, 61 tables;
- the first attempt exposed a procedure defect, now corrected.

**Not yet:** against Supabase.

### 9. Hosting (VPS): AWAITING PRODUCT OWNER

**Needed:** specifications, location and what else runs there (plan §3). Option B (Render) is the fallback; the images work on both.

### 10. Container images: PREPARED

**Prepared:**
- `deploy/backend.Dockerfile`, `deploy/frontend.Dockerfile`, `.dockerignore`;
- CI job `container-images`. It:
  - validates the compose file;
  - builds both images;
  - confirms the backend image refuses three unsafe staging configurations;
  - runs migrations, API and worker from the image against PostgreSQL;
  - checks `/health/worker` = 200 and `/me` = 401;
  - crashes the worker process and checks Docker restarts it and monitoring recovers;
  - checks neither image contains an env file.

**Evidence:** CI runs 41766998942 and 41768132124 (§ CI record). Docker is not installed on this workstation, so the images were not built locally.

### 11. HTTPS and routing: PREPARED

`deploy/Caddyfile`:
- automatic Let's Encrypt certificates;
- HSTS and security headers;
- `noindex`.

**Needs:** a domain with two DNS records (guide §2).

### 12. Worker supervision: PREPARED

**Prepared:**
- the compose file sets `restart: unless-stopped` and `init: true`, with a 30-second graceful stop;
- stalls are caught by `/health/worker` (item 13).

**Evidence:** the CI crash-and-restart step passed in both runs: the worker process was SIGKILLed, Docker restarted the container, and `/health/worker` returned 200 again. Not yet shown on a real host.

### 13. Uptime monitoring: AWAITING PRODUCT OWNER

**Needs:** an uptime-monitor account (free tiers exist) and the address alerts go to (guide §3).

### 14. Logging and alerting: PREPARED (logs) / NOT STARTED (central alerting)

**Prepared:**
- rotated JSON logs per service;
- Caddy access logs;
- the worker logs each degraded condition once.

Central log shipping is not started; the uptime alert comes first.

### 15. Secrets handling: PREPARED

**Prepared:**
- templates contain placeholders only;
- `.env*` is gitignored, and the templates are tracked deliberately;
- `with_env` refuses a file git would commit and never prints values;
- `check_staging` hides passwords and keys (tested);
- the CI image check fails if an env file reaches an image.

### 16. MiniMax: AWAITING PRODUCT OWNER

**Prepared (WP3):**
- adapter;
- `check_model_provider`, for model availability and one synthetic call;
- `evaluate_recovery_model`: 14 synthetic scenarios × 3 repeats, measuring structured-output validity, injection, invented figures, unsupported claims, fallbacks, latency, tokens and estimated cost, within a USD budget;
- fallback monitoring.

**Data handling:**
- MiniMax publishes no zero-retention option;
- its API terms (dated 30 March 2026, per secondary sources; read the original) allow use for service improvement;
- data is stored in the United States.

**Recommendation:** synthetic data only, unless a data processing agreement says otherwise.

**Not yet:** any call. No key is configured.

### 17. Nebius Token Factory: AWAITING PRODUCT OWNER

**Prepared:** as item 16.

**Data handling:**
- Nebius states it does not train on API data;
- **inputs and outputs are kept by default** (speculative decoding) unless **Zero Data Retention** is switched on in the account profile.

**Recommendation:** switch on Zero Data Retention before any evaluation run.

**Not yet:** any call. No key is configured.

### 18–21. NOT STARTED

No work requested yet. Item 20 waits for WP5 M3's channel decision. Item 21 builds on the ingestion API (plan §10).

### 22. GitHub Actions CI: VERIFIED

The `verify` job runs on every push:
- backend on PostgreSQL;
- frontend lint, typecheck, unit tests and production build check;
- browser E2E.

The last WP4 run passed (run 41671496065).

## CI record

| Commit | Run | Result |
|---|---|---|
| `800f318` | [41766998942](https://github.com/TopRam3n/Koro-Farm/actions/runs/41766998942) | `verify` passed. `container-images`: every step passed (images built; unsafe staging configurations refused; migrations, API and worker ran from the image; `/health/worker` 200; `/me` 401; the crashed worker was restarted and monitoring recovered) **except** the env-file scan. That scan searched the whole image filesystem. Its log needs authentication, so the matching file is unknown; it was outside the application directories, which are the only place build-context files land |
| `00f9943` | [41768132124](https://github.com/TopRam3n/Koro-Farm/actions/runs/41768132124) | **Passed, both jobs.** The env-file scan now covers `/srv` and `/app` and reports any match as an annotation |
