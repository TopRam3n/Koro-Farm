# R1 — Infrastructure plan: isolated staging

**Status (3 November 2026):**
- Prepared in code and configuration.
- **Nothing is connected to a real external service, nothing is deployed, and no paid resource exists.**
- Branch `feat/r1-staging-infrastructure`, built on WP4 (`267ac9c`). Not merged.

**Related documents:**
- [R1_INTEGRATION_READINESS.md](R1_INTEGRATION_READINESS.md): the status of every integration, with evidence.
- [R1_PRODUCT_OWNER_SETUP_GUIDE.md](R1_PRODUCT_OWNER_SETUP_GUIDE.md): the steps that need you.

**Goal:** move KoroFarm from a locally tested application to an isolated, verifiable staging system with:
- a real database;
- real authentication;
- a supervised worker;
- evaluated AI providers.

It must not become a production service before it is approved as one.

## 1. Audit summary

| Area | Implemented and tested | Simulated or stand-in | Needs an external account | Needs a deployment decision |
|---|---|---|---|---|
| **Database** | PostgreSQL 17 schema; Alembic chain 0001–0026; locking and races tested on real PostgreSQL | none | Supabase project | region, plan |
| **Authentication** | The API checks every bearer token with Supabase; memberships; tenant isolation (tests on SQLite and PostgreSQL) | **CI and E2E use a test-only auth stand-in** (`auth-stub.mjs`) | Supabase Auth, users | sign-up policy |
| **Frontend** | Next.js production build; check that no test-auth code ships | none | none | hosting |
| **API and worker** | Health endpoints; heartbeats; `/health/worker` returns 503 unless OPERATIONAL | **No process supervisor existed** (added here, see §4) | none | hosting |
| **Model providers** | MiniMax and Nebius adapters; structured-output validation; synthetic evaluation harness; cost estimates; fallback monitoring | **Never called a real provider** (no keys configured) | API keys | data-handling approval |
| **Backups** | The pg_dump and pg_restore procedure, rehearsed on local PostgreSQL 17 | — | Supabase backups | plan |
| **Monitoring** | Health endpoints; the worker logs degraded conditions | **No alert channel** | an uptime-monitor account | alert recipient |

### Defects and gaps found and fixed in this round

1. **Supabase's Data API would have exposed every KoroFarm table.**
   - Supabase serves the `public` schema over HTTPS to the `anon` and `authenticated` roles. Those roles are reached with the publishable key, which every browser holds.
   - KoroFarm's tables live in `public` with no row-level security. Supabase's default grants would have given those roles full access to every table, bypassing authentication, tenancy and every business rule.
   - **Fix:** migration `0026` and `app/infrastructure/database/data_api.py`.
     - Applies only where Supabase's roles exist, so CI and local databases are unaffected.
     - Revokes every client-role privilege, now and for future tables.
     - Enables row-level security, with no policies, on every table. The backend connects as the table owner, which RLS does not restrict.
   - **Plus:** the setup guide switches the Data API off in the dashboard.
   - **Checked by:** `check_staging` (grants, and an HTTP probe with the publishable key).
2. **Staging could have started against the development database.**
   - `DATABASE_URL` silently fell back to `korofarm:korofarm@localhost`.
   - Staging and production now refuse to start unless `DATABASE_URL` meets all of these:
     - it is set explicitly;
     - it does not use the development credentials;
     - it requires TLS (`sslmode=require` or `verify-full`) for a remote host.
3. **Alembic failed on URL-encoded passwords.**
   - A password containing `@`, `%` or similar characters is URL-encoded, and configparser rejected the result ("invalid interpolation syntax").
   - Reproduced on PostgreSQL, then fixed. The test fails without the fix.
4. **Supabase's transaction pooler does not support prepared statements.**
   - psycopg prepares statements automatically, so the transaction pooler (port 6543) would have failed under load.
   - Prepared statements are now switched off automatically for port 6543.
   - Pool size, overflow, recycle time, connect timeout and a per-process `application_name` (`korofarm-api`, `korofarm-worker`) are configurable.
5. **A hard-coded personal email was the default access-request reviewer** in both the API and the UI.
   - Removed. With no reviewer configured, nobody can review requests (fail closed).
   - The address remains in git history; rewriting public history is not proposed.
6. **No deployment configuration, environment templates or provisioning existed.**
   - The README told readers to copy a `.env.example` that did not exist. Added (§4).
7. **A model provider could have been switched on in staging with no record of approval.**
   - Staging now refuses to start with `AGENT_MODEL_PROVIDER` set unless `AGENT_MODEL_STAGING_APPROVAL` holds your recorded approval reference. Production refuses a provider outright, as before.
8. **The documented restore procedure did not work.**
   - Restoring a dump of the `public` schema into any new database (every Supabase project included) failed on `CREATE SCHEMA public`.
   - Found by rehearsing the procedure; corrected in §6.

### Does a pilot database exist?

**No evidence that one exists.** On this workstation:
- no `DATABASE_URL` points anywhere but local development and the disposable test instance;
- no deployment, hosting or Supabase project is configured;
- the frontend's local settings point at local demo stand-ins.

WP4 described the pilot database as "not reachable from this workstation". That was an assumption, not an observation.

- **Plan:** treat staging as a **new, empty database**. The release audit has nothing to correct on a database that never held pre-WP4 orders. A dry run on new staging will show empty results, which is a useful sanity check, not a correction.
- **Needs your confirmation:** whether any database with real pilot records exists anywhere (guide, step 0).

## 2. Recommended staging architecture

```text
                       ┌──────────────── Supabase project "korofarm-staging" (East US) ───────────────┐
 Browser ──HTTPS──► Caddy ─► Next.js frontend           Auth (email + password)    PostgreSQL 17       │
 (staff, buyers)       │                    ▲                   ▲                   ▲  Data API OFF     │
                       └─► FastAPI API ─────┼── token check ────┘                   │  RLS on, no grants│
                              (uvicorn)     └───────── SQL over TLS (session pooler, port 5432) ───────┘
                           Worker (same image; Docker restarts it)───────────────────┘
 Uptime monitor ──► https://api.<domain>/health/worker   (alerts when not 200)
```

**Principles:**
- One backend image serves both the API and the worker, so they always run the same code.
- Migrations are an explicit step, taken after a backup, never run on start.
- Staging and production never share a Supabase project or a database.
- No secret is baked into an image or committed. Secrets live in your password manager and in `deploy/.env` on the server (mode 600).
- Staging holds synthetic data until a separate decision allows otherwise.

### Hosting options

| Option | Fits when | Monthly cost (estimate) | For | Against |
|---|---|---|---|---|
| **A. Your VPS: Docker Compose and Caddy** (`deploy/`) | The VPS meets §3, and you are comfortable with SSH and Docker | Spare capacity: $0 extra. A new small VPS: about $6–25 | Cheapest; one place; portable | You patch the operating system; one machine is a single point of failure |
| B. Render (API and worker) plus Vercel or Render (frontend) | The VPS is unsuitable, or you prefer managed hosting | About $14 (two Starter services at about $7 each, unverified for workers) plus frontend $0–20 | Managed TLS, restarts and deploys | More accounts; Vercel Hobby forbids commercial use (Pro is $20 per seat) |
| C. Managed containers (Fly.io, Cloud Run, ECS) | Later, for production scale | Varies | Scales out | More set-up than staging needs |

**Recommendation:**
- **Option A, if your VPS meets §3**, with the VPS in or near **US East** to keep it close to the Supabase project. Every API request makes database calls plus one call to Supabase Auth, so the distance matters.
- **Otherwise option B.** The same images and environment variables work on both, so moving later is a configuration change.

### Database plan

- **Free plan** to connect and verify. It costs nothing.
  - Free projects **pause after about a week of inactivity**.
  - They have no backups suitable for data you care about.
- **Pro plan**, about $25 a month for the organization, before staging must stay up continuously or holds anything worth keeping.
  - It includes compute credit for one Micro instance and daily backups. Retention is shown under Database > Backups.
  - Point-in-time recovery is a separately priced add-on, not needed for staging.

## 3. Your VPS: what I need to know before recommending it

I have not seen its specifications, so it is **not assumed suitable**. Please report:

| Item | Minimum for staging | Why |
|---|---|---|
| CPU and RAM | 2 vCPU, 4 GB RAM (2 GB works if the frontend image is built elsewhere) | `next build` needs about 2 GB; at runtime the services use about 1.7 GB in all (limits in the compose file) |
| Disk | 20 GB free | Images, logs (rotated: 5 × 10 MB per service), backups if kept locally |
| Operating system | Ubuntu 22.04 or 24.04 LTS, or Debian 12, with security updates | Docker Engine and Compose v2 |
| Location | US East, or as close to Jamaica and the Supabase region as possible | Latency on every request |
| Network | Public IPv4; ports 80 and 443 open inbound; SSH restricted to keys | Caddy's automatic HTTPS; Supabase's shared pooler is IPv4 |
| What else runs there | Anything else on the machine | Ports 80 and 443 must be free for Caddy, or an existing proxy must route to the stack; shared risk |
| Access | Who has root or sudo; backup or snapshot facility | Recovery |

## 4. What was prepared (in this branch)

| Item | Where |
|---|---|
| Backend image (API, worker and operations commands; non-root; pg_dump included; health check) | `deploy/backend.Dockerfile` |
| Frontend image (live mode only; fails if test-auth code reaches the bundle) | `deploy/frontend.Dockerfile` |
| Compose stack: Caddy, frontend, API, worker; `migrate` and `check` operations profile | `deploy/compose.staging.yml` |
| Automatic HTTPS, security headers, `noindex`, JSON access logs | `deploy/Caddyfile` |
| Build context that excludes `.env*`, `node_modules`, tests and artefacts | `.dockerignore` |
| Environment templates (placeholders only) | `deploy/.env.example`, `src/backend/.env.example`, `src/frontend/.env.example` |
| Fail-closed configuration: database URL, TLS, model approval | `app/core/config.py` |
| Pooler-aware connections and pool settings | `app/infrastructure/database/session.py` |
| Data API lockdown: migration, check, re-apply command | `alembic/versions/0026_…`, `data_api.py`, `scripts/data_api_lockdown.py` |
| Read-only staging check (configuration, database, TLS, migrations, Data API, Auth settings, health, worker, CORS, model) | `scripts/check_staging.py` |
| Organization, account and membership provisioning (dry run by default; never resolves conflicts) | `scripts/provision_staging.py` |
| Run a command with a gitignored env file, on PowerShell or bash | `scripts/with_env.py` |
| CI job: builds both images, enforces the staging rules in the image, runs migrations, API and worker from the image, crashes the worker and checks Docker restarts it, checks images contain no env files | `.github/workflows/competition-readiness.yml`, job `container-images` |

## 5. Deployment procedure (VPS; not to be run without authorization)

Each step's success is checked before the next.

1. **Prepare the server:**
   - install Docker Engine and Compose v2;
   - create a non-root `korofarm` user in the `docker` group;
   - enable the firewall (22 for your key only; 80 and 443);
   - turn on automatic security updates.
2. **Point DNS at the server:** `staging.<domain>` and `api.staging.<domain>`.
3. **Get the code:** clone the repository at the exact commit being staged; record the commit.
4. **Fill in the environment:** `cp deploy/.env.example deploy/.env`; `chmod 600 deploy/.env`; fill it in on the server from your password manager.
5. **Build:** `docker compose -f deploy/compose.staging.yml --env-file deploy/.env build`.
6. **Back up** (§6). Skip on the very first deployment, when the database is empty.
7. **Migrate:** `docker compose … --profile ops run --rm migrate`. Record the output.
8. **Provision** organizations and memberships:
   - `docker compose … run --rm -v /path/plan.json:/plan.json:ro api python -m src.backend.scripts.provision_staging /plan.json` (dry run);
   - then the same command with `--apply`.
9. **Start the stack:** `docker compose … up -d`.
10. **Check:** `docker compose … --profile ops run --rm check`. Every line must be PASS, apart from the WARNs you have accepted.
11. **Run the staging authentication test** from your machine (`docs/product/STAGING_AUTH_VERIFICATION.md`). All 5 checks must pass.
12. **Set the uptime monitor** on `https://api.staging.<domain>/health/worker`.

**Rollback:**
- **Code:** check out the previous commit, rebuild, `up -d`. Images are tagged `${RELEASE}`, so keep the previous tag.
- **Database:**
  - migrations are additive by design, so the previous code runs on the newer schema;
  - downgrades are not used on shared data;
  - if data must go back, restore the pre-migration backup into a **new** project, check it, then switch `DATABASE_URL` to it.

**Recovery:**

| Failure | What happens | What to do |
|---|---|---|
| Worker crashes | Docker restarts it | Nothing |
| Worker stalls (alive but not beating) | `/health/worker` turns 503 and the monitor alerts | `docker compose restart worker` |
| Host reboots | All services restart (`restart: unless-stopped`) | Nothing |
| Database unreachable | `/health/worker` 503; API requests fail | Check Supabase status and network restrictions |

## 6. Backups and restoration

**Supabase:** Pro takes daily backups. Free has no backups to rely on.

**Our own logical backup** (before every migration, and weekly), from any machine with PostgreSQL 17 client tools:

```bash
# The backup URL is the session-pooler URL without "+psycopg"; the password comes from PGPASSWORD or a prompt.
pg_dump --format=custom --schema=public --no-owner --no-privileges \
  --file=korofarm-staging-$(date +%Y%m%d-%H%M).dump "postgresql://postgres.<ref>@<pooler-host>:5432/postgres?sslmode=require"
pg_restore --list korofarm-staging-<…>.dump | head        # readable
```

Store dumps encrypted (password manager attachment, or an encrypted bucket), never in the repository.

**Restore into a NEW database or project** (never over a live one):

```bash
pg_restore --list korofarm.dump | grep -v " SCHEMA - public " > restore.list   # every new database already has public
pg_restore --no-owner --no-privileges --exit-on-error --single-transaction --use-list=restore.list \
  --dbname="postgresql://postgres.<new-ref>@<pooler-host>:5432/postgres?sslmode=require" korofarm.dump
python -m src.backend.scripts.data_api_lockdown           # dry run, then --apply: the new project's default grants
python -m src.backend.scripts.check_staging               # migrations at head, nothing exposed
```

**Rehearsed on 3 November 2026 on the local disposable PostgreSQL 17 instance**, not on Supabase:
- migrated a database to `0026` and provisioned an organization, account and membership;
- dumped it, and restored it into a second database with the filtered list;
- the result was identical: same Alembic revision, same row counts, 61 tables. Alembic reports `0026 (head)` on the restored copy;
- the first attempt, without the filtered list, failed on `CREATE SCHEMA public`, which is why that step exists.

**Not yet done:** the same rehearsal against a real Supabase project.

## 7. Environments

| | Development | Test (CI) | Staging | Production |
|---|---|---|---|---|
| `APP_ENV` | development | test | staging | production |
| Database | local PostgreSQL | disposable PostgreSQL | Supabase project `korofarm-staging` | separate Supabase project (later) |
| Authentication | your own Supabase project or Supabase CLI | test-only stand-in | real Supabase Auth | real Supabase Auth |
| Demo or insecure auth | refused | stand-in only (`APP_ENV=test`) | refused | refused |
| Data | synthetic | synthetic | synthetic until a decision | real, after approval |
| Model provider | allowed (synthetic) | stubbed | only with `AGENT_MODEL_STAGING_APPROVAL` | refused |

## 8. Operations: monitoring, logging, alerting, secrets

- **Health:**
  - `/health` shows whether the API process is up.
  - `/health/worker` shows whether exception monitoring is OPERATIONAL. It returns 503 with reasons otherwise, and carries no tenant data. The uptime monitor watches it.
- **Logs:**
  - every container logs to Docker's json-file driver, rotated (5 × 10 MB);
  - Caddy writes JSON access logs, and by default leaves out Authorization and Cookie headers;
  - the worker logs each degraded condition once;
  - model calls never log keys or reasoning (`scrub()`).
  - **Not yet:** central log shipping. The first step is an uptime monitor with an email alert; log shipping can follow if needed.
- **Secrets:**
  - kept in your password manager and in `deploy/.env` on the server (mode 600, gitignored);
  - the CI image check fails if an env file reaches an image;
  - Supabase's secret key is **not used** by KoroFarm and should not be copied anywhere.
- **Known limitation (debt item 29):**
  - The API checks each token with Supabase over HTTPS, which adds a round trip per request. It also means sign-out takes effect immediately, if Supabase refuses ended sessions (staging authentication check 5).
  - Local JWT verification with Supabase's signing keys would remove the round trip. It is deferred until the staging measurements show whether it is needed.
- **Least privilege (debt item 30):** the backend connects as Supabase's `postgres` role, the table owner. A dedicated owner role with fewer powers is planned before production.

## 9. Estimated monthly operating cost (USD; assumptions stated)

**Assumptions:**
- prices from public pricing pages and third-party summaries read on 3 November 2026; **verify on each provider's page before buying**;
- staging only, with low traffic;
- a $10–15 per year domain, if you need one, is not included.

| Item | Low | Recommended | Notes |
|---|---|---|---|
| Supabase | $0 (Free: pauses, no backups) | $25 (Pro, one Micro project) | A later production project adds its own compute, about $10 or more |
| Hosting | $0 (spare VPS capacity) | $6–25 (small VPS) or about $14–34 (Render, plus Vercel Pro) | |
| Uptime monitor | $0 (free tiers) | $0 | Check the free tier's terms |
| Email for Auth | $0 (Supabase's built-in email, rate-limited, for testing only) | $0–20 (custom SMTP) | Only needed if people sign up or reset passwords by email at scale |
| Model evaluation (synthetic) | $0 | ≤ $2 per full run | The harness stops at `--max-usd` (default 2.00); prices from `pricing.py` (list prices, 31 October 2026) |
| **Total** | **$0** | **about $31–60** | |

## 10. Future integrations: architecture

KoroFarm's integrations follow the pattern the model providers already use:
- **Behind a narrow adapter:** one module per external system, holding no business logic (like `agents/infrastructure/providers.py`).
- **Configuration and secrets:** from the environment only.
- **Validation:** everything that comes back is validated before use.
- **Failure:** any failure degrades to a deterministic or manual path, never to an unsafe action.

| Direction | Mechanism already in the code | Rules that stay |
|---|---|---|
| **Outbound:** messages to farmers and buyers (SMS, WhatsApp, email), partner notifications | Transactional outbox (`infrastructure/outbox`) and `OutboundMessage` records | Sent only after the existing approval; recorded consent to contact; delivery status recorded; nothing sent from production until authorized (WP5 M3) |
| **Inbound:** agricultural data sources, field reports, partner systems | Ingestion API with idempotency, provenance and secure action links (`docs/integrations/INGESTION_API.md`) | Organization-scoped; untrusted until verified; no automatic supplier activation |
| **Institutional:** government, programmes | Organization-scoped records and audit events | Each integration gets its own entry in the readiness document, its own credentials and a synthetic sandbox first |

**Each new integration starts NOT STARTED in [R1_INTEGRATION_READINESS.md](R1_INTEGRATION_READINESS.md)** and moves through PREPARED, AWAITING PRODUCT OWNER, CONNECTED and VERIFIED, each with evidence.

## 11. WP5 relationship

WP5 remains separate. Planning priority:
- **M1** role-aware workspace;
- **M2** buyer portal;
- **M3** external notifications and supplier consent. M3 builds on the outbound pattern in §10.

M4–M7 are deferred until the staging baseline exists, unless a demonstrated pilot dependency requires them. **No WP5 feature is implemented.**
