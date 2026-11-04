# R1 — Product-owner setup guide (staging)

This guide covers the steps that need your accounts, your decisions or your money.

**Order:**
1. Step 0 (a question).
2. Supabase.
3. Hosting and domain.
4. Uptime monitoring.

MiniMax and Nebius (§4, §5) are independent and can be done at any time.

**Rules for every step:**
- **Never paste a key, password or connection string into chat, an issue, a pull request or a commit.**
- Credentials go in your password manager first. From there they go only into a local gitignored file or the server's `deploy/.env`.
- Every check below prints PASS, FAIL, WARN or SKIP with no secret in it, so its output is safe to share. Glance over it before sharing anyway.
- Nothing here deploys KoroFarm or enables production model use. Deployment needs a separate go-ahead.

**Local secrets file:** the tools read `src/backend/.env.staging.local`.
- Any name starting `.env.` is gitignored, and the runner refuses a file git would commit.
- Start it from `deploy/.env.example`. The same commands work in PowerShell and bash:

```text
python -m src.backend.scripts.with_env --names src/backend/.env.staging.local -- python -m src.backend.scripts.check_staging
```

## Step 0. Does a pilot database with real records exist?

I found no sign of one, so the plan treats staging as a new, empty database.

- **If there is none:** tell me "no pilot database". The release audit is then unnecessary.
- **If there is one:** tell me where it is hosted, but **not** its credentials. The WP4 backup and read-only dry run then apply, and `--apply` stays unauthorized.

## 1. Supabase (database and sign-in)

| | |
|---|---|
| **Website** | https://supabase.com/dashboard |
| **Create** | an account (if you have none), an organization and **one project, `korofarm-staging`** |
| **Cost** | Free plan: $0, but it pauses after about a week of inactivity and has no backups to rely on. **Pro: about $25 a month per organization** (includes one Micro project); confirm on supabase.com/pricing. Start on Free if you prefer, and upgrade before staging must stay up |
| **Store** | the database password, the project ref, the session-pooler connection string and the publishable key, all in your password manager |

### 1.1 Create the project

1. In your organization, choose **New project**.
2. Fill in the form:
   - **Name:** `korofarm-staging`.
   - **Database password:** use **Generate a password**, then save it in your password manager straight away.
   - **Region:** **East US (North Virginia)**, the closest to Jamaica, and where the server should also be.
3. If the form offers a choice of connection methods or Data API exposure, choose **connection string only / no Data API**.

### 1.2 Database security

1. **Database > Settings > SSL Configuration:** turn on **Enforce SSL on incoming connections**.
2. **Database > Settings > Network Restrictions** (once the server exists):
   - allow only the server's IP address, plus your own while you do maintenance;
   - until then, leave it open. The password and TLS still protect it.

### 1.3 Switch off the Data API

**Why:** KoroFarm talks to its database only through its own API. Supabase's Data API would otherwise publish tables over HTTPS to anyone holding the public key. Migration 0026 also locks this down, but both layers should be in place.

1. In the project's **Data API** settings (under Integrations or Project Settings, depending on dashboard version):
   - turn **Enable Data API** off;
   - if the option is still visible, turn **Automatically expose new tables** off.
2. Leave **Auth** on: sign-in uses Supabase's Auth service, not the Data API.

### 1.4 Authentication settings

**Authentication > Sign In / Providers:**
- **Email** enabled.
- **Confirm email:** on.
- **Allow new users to sign up:** **off** for staging. You will create users yourself.
  - Self-service access requests need sign-up on. Turn it on only if you want to test that flow.
- **Password requirements:** minimum length 12; turn on leaked-password protection if your plan offers it.

**Authentication > URL Configuration:**
- **Site URL:** `https://staging.<your-domain>`. Use a placeholder until the domain exists, and update it later.
- **Redirect URLs:** the same address only. Don't add localhost to the staging project.

### 1.5 Create the three test users

These are needed by the staging authentication test.

1. Go to **Authentication > Users > Add user > Create new user**.
2. For each user:
   - use an email you control (plus-addresses like `you+coordA@…` work);
   - generate a strong password into your password manager;
   - tick **Auto Confirm User**.

| Label | Purpose |
|---|---|
| `coordinator_a` | supply coordinator, organization A |
| `colleague_a` | auditor, organization A (the control for the same-organization check) |
| `coordinator_b` | supply coordinator, organization B (the cross-tenant check) |

3. Copy each user's **User UID**. These are not secrets.

### 1.6 Provisioning plan

1. Create the plan file **outside the repository**, for example `Documents/korofarm-staging-plan.json`. It holds names and emails.
2. Fill it in:

```json
{
  "organizations": [
    {"slug": "staging-org-a", "name": "Staging Organization A"},
    {"slug": "staging-org-b", "name": "Staging Organization B"}
  ],
  "users": [
    {"id": "<User UID of coordinator_a>", "email": "<email>", "display_name": "Coordinator A",
     "memberships": [{"organization": "staging-org-a", "role": "SUPPLY_COORDINATOR"}]},
    {"id": "<User UID of colleague_a>", "email": "<email>", "display_name": "Colleague A",
     "memberships": [{"organization": "staging-org-a", "role": "AUDITOR"}]},
    {"id": "<User UID of coordinator_b>", "email": "<email>", "display_name": "Coordinator B",
     "memberships": [{"organization": "staging-org-b", "role": "SUPPLY_COORDINATOR"}]}
  ]
}
```

**What the plan file contains:**
- No passwords: the script refuses any.
- Staff roles only. Farmers and buyers join through the in-app invitation.

### 1.7 Keys and connection string

**Project Settings > API Keys:**
- **Publishable key** (`sb_publishable_…`): public by design; it goes in the browser bundle. Save it.
- **Secret key** (`sb_secret_…`) and the legacy `service_role` key: **KoroFarm does not use them. Do not copy them anywhere.**

**Connect** button (top of the project) > **Session pooler**:
1. Copy the URI. It looks like `postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres`.
2. Change the start to `postgresql+psycopg://`.
3. Put in the password. URL-encode special characters: `@` → `%40`, `#` → `%23`, `%` → `%25`, `/` → `%2F`.
4. Add `?sslmode=require` at the end.

Use the **session pooler (port 5432)**, not the transaction pooler (6543): migrations need it, and it works over IPv4.

### 1.8 Fill the local file and check the connection (read-only)

1. Create `src/backend/.env.staging.local`, copying the variable names from `deploy/.env.example`:
   - `APP_ENV=staging`;
   - `DATABASE_URL=<the URL from 1.7>`;
   - `SUPABASE_URL=https://<ref>.supabase.co`;
   - `SUPABASE_PUBLISHABLE_KEY=<publishable key>`.
2. Run:

```text
python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.check_staging
```

**Expected on a brand-new project:**

| Check | Expected | Why |
|---|---|---|
| `configuration` | PASS | |
| `database` | PASS (PostgreSQL 17, session pooler or direct) | |
| `database_tls` | PASS | |
| `migrations` | **FAIL**: "no alembic_version table; run the migrations" | Correct: nothing is installed yet |
| `data_api_http` | PASS, or WARN if the Data API is still on | |
| `auth_settings` | PASS, or WARN if sign-up is open or confirmation is off | |

Send me that output. It contains no secrets.

**This step is CONNECTED for database and Auth settings.** It is VERIFIED only after migrations, provisioning and the authentication test.

### 1.9 Install the schema and the staging accounts (needs your go-ahead)

This writes to the new, empty staging project only. Once you say go, either of us runs:

```text
python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m alembic -c src/backend/alembic.ini upgrade head
python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.provision_staging <path-to-plan.json>
python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.provision_staging <path-to-plan.json> --apply
python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.check_staging
```

**What success looks like:**
- Alembic ends at `0026_supabase_data_api_lockdown`.
- The provisioning dry run lists 2 organizations, 3 accounts and 3 memberships to create; `--apply` prints `applied`.
- The final check shows `migrations` PASS and `data_api_grants` PASS ("roles anon, authenticated, service_role hold no privilege; every table has RLS").

### 1.10 Backups

- **Pro:** daily backups are listed under **Database > Backups**.
- **Either plan:** we take our own `pg_dump` before every migration (infrastructure plan §6). Keep the dumps encrypted in your password manager or an encrypted bucket, never in the repository.

## 2. Hosting and domain

### 2.1 Your VPS (option A, preferred if suitable)

Please send me the specifications listed in the infrastructure plan §3:
- CPU, RAM and disk;
- operating system and version;
- location and provider;
- public IPv4;
- what else runs on it;
- who has root;
- whether snapshots are available.

These are not secrets. **Don't send** the root password or SSH private key.

**If it is suitable, for when deployment is authorized:**
- **Server user:** create a non-root user named `korofarm`, with SSH key login only.
- **Firewall:** port 22 open to your IP; 80 and 443 open to everyone.
- **Docker:** install Docker Engine and Compose v2.
- **Cost:** none, if the VPS has spare capacity.

### 2.2 Domain and DNS

| | |
|---|---|
| **Where** | your domain registrar's DNS settings |
| **Create** | two records pointing at the server's IPv4 address: `staging.<domain>` and `api.staging.<domain>` (type A) |
| **Cost** | none if you own a domain; a new one is about $10–15 a year |
| **Also send me** | the domain names (not secret), and an email address for certificate expiry notices |

### 2.3 Server secrets (at deployment time)

1. On the server, `deploy/.env` is copied from `deploy/.env.example` and filled in **by you, on the server**, from your password manager.
2. Set its mode with `chmod 600`.
3. It is gitignored.

The same values as your local file, plus the two domains and the ACME email.

### 2.4 Option B, if the VPS is unsuitable

Render (API and worker) plus Render or Vercel (frontend):
- **Cost:** about $14–34 a month. Vercel's free Hobby plan does not allow commercial use.
- **Instructions:** I'll write the click-by-click steps if you choose this route. The images and variables are the same.

## 3. Uptime monitoring and alerts

| | |
|---|---|
| **Website** | any uptime monitor with a free tier (for example UptimeRobot or Better Stack); check its terms |
| **Create** | one HTTP monitor on `https://api.staging.<domain>/health/worker`, alerting when the response is **not 200**, checking every 1–5 minutes |
| **Alert recipient** | the email or phone of whoever will respond |
| **Cost** | $0 on free tiers |
| **Success** | the monitor is green while the worker runs, and turns red within a few minutes of `docker compose stop worker` (test this once) |

The endpoint shows no tenant data and needs no credentials.

## 4. MiniMax (synthetic evaluation only)

| | |
|---|---|
| **Website** | https://platform.minimax.io (international platform) |
| **Create** | an account and an API key; add a small prepaid balance if required |
| **Cost** | a full synthetic run is capped at an estimated $2 (`--max-usd`). Set a spending limit or a small balance in the console |
| **Privacy (read first)** | MiniMax publishes no zero-retention option, and its API terms allow use for service improvement. **Synthetic data only.** No real farmer, buyer or commercial data is sent without a data processing agreement and your approval |
| **Store** | the key in your password manager, then in `src/backend/.env.staging.local` as `MINIMAX_API_KEY=` and `MINIMAX_MODEL=MiniMax-M3` |

**Test** (synthetic, development mode, prints no key):

```text
python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.check_model_provider --provider minimax --no-call
python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.check_model_provider --provider minimax
```

The scripts refuse `APP_ENV=production`; `staging` is fine for these synthetic calls.

**What success looks like:**
- `key_present: True`;
- `model offered to this account: True`;
- `synthetic request: outcome=answered mode=model …`.

**Then the evaluation:** `python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.evaluate_recovery_model --provider minimax --repeats 3 --max-usd 1.00`.
- It produces JSON and Markdown reports with no keys.

## 5. Nebius Token Factory (synthetic evaluation only)

| | |
|---|---|
| **Website** | https://tokenfactory.nebius.com |
| **Create** | an account and an API key |
| **Privacy setting** | **turn on Zero Data Retention in your account profile before any call.** Without it, Nebius keeps inputs and outputs (it states it does not train on them) |
| **Cost** | as MiniMax: capped per run; add a small balance or a limit |
| **Store** | `NEBIUS_API_KEY=` and `NEBIUS_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507` in the same local file |
| **Test** | as §4 with `--provider nebius`; success also shows the `structured_mode` the model accepted |

**Staging use of a model, later:**
- It needs your written approval recorded as `AGENT_MODEL_STAGING_APPROVAL=<your reference>`; without it the API refuses to start.
- Production stays refused outright.
- Model output never bypasses human approval, consent, quantity conservation or execution safeguards. Those are enforced in code regardless of the model.

## What I need from you next

**First:**
- Step 0 answer.
- Create the Supabase project (§1.1–1.7).
- Run the read-only check (§1.8) and send me its output.

**Then:**
- your go-ahead for §1.9;
- the VPS specifications (§2.1);
- the domain names (§2.2).
