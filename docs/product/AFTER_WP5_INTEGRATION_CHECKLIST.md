# After WP5: integration checklist

**Purpose:** the order in which KoroFarm's external services are connected and verified, now that WP5 is implemented
offline.

**Who acts:**
- **PO:** product owner.
- **ENG:** engineering.

**Status words** (as in `R1_INTEGRATION_READINESS.md`):
- PREPARED: built and tested locally or in CI.
- CONNECTED: talked to the real service.
- VERIFIED: acceptance checks passed against the real service.

**Fixed rules for every step:**
- Credentials never go into the repository, chat, issues or pull requests.
- Each deployment, schema installation on a shared system, paid resource and live data flow needs the PO's explicit
  go-ahead at that step.
- Nothing here relaxes a WP1–WP5 safeguard.

## 0. Before anything is connected (PO)

- [ ] Confirm whether a pilot database with real records exists (setup guide, step 0).
- [ ] Merge decision: review and merge the branch stack in order:
  1. WP1;
  2. WP2;
  3. WP3;
  4. model providers;
  5. WP4;
  6. staging infrastructure;
  7. WP5.

  Merges are never automatic.

## 1. Supabase project and authentication

- [ ] **PO:** create the staging project, users and settings: setup guide §1.1–1.8, including §1.3 (Data API off) and
  §1.4 (asymmetric JWT signing key).
- [ ] **PO:** run `check_staging` read-only (§1.8) and send the output.

  **Expected:**
  - `auth_signing_keys`, `auth_session_store` and `data_api_http` PASS;
  - `migrations` FAIL, because nothing is installed yet;
  - `data_api_grants` FAIL, because Supabase's default grants are still in place.
- [ ] **ENG:** if `data_api_http` answers "unrecognized", adjust the classifier to the observed disabled-Data-API
  response. This is the one untested assumption: setup guide §1.11.

## 2. Database setup (PO go-ahead required)

- [ ] **ENG/PO:** back up (empty project: a baseline dump).
- [ ] **ENG:** `alembic upgrade head`, reaching `0029_agricultural_intelligence`. Reviewed SQL: `deploy/sql/`.
- [ ] **ENG:** `check_staging`: `migrations` and `data_api_grants` PASS (Data API audit including the future-object
  probe and the closed `agri` schema).
- [ ] **ENG:** provision staging organizations and accounts: dry run, then `--apply` (§1.9).
- [ ] **ENG:** rehearse backup and restore against the real project (infrastructure plan §6), then re-run
  `data_api_lockdown` and `check_staging`.

## 3. Hosting

- [ ] **PO:** VPS specifications, or approval of the managed fallback; domain and DNS; an uptime monitor on
  `/health/worker` (setup guide §2–3).
- [ ] **PO:** deployment go-ahead.
- [ ] **ENG:** deploy the compose stack:
  - `NOTIFICATION_PROVIDER=none`;
  - `AGENT_MODEL_PROVIDER=none`;
  - `AGRI_LLM_ENABLED=false`;
  - `AUTH_SESSION_VERIFICATION` unset.
- [ ] **ENG:** `check_staging --api-url … --frontend-origin …`: every check PASS. Confirm worker supervision and the
  uptime alert on the real host.

## 4. Staging authentication release gate

- [ ] **ENG/PO:** `npm run test:staging-auth` against the deployed system (`STAGING_AUTH_VERIFICATION.md`):
  - wrong password;
  - sign-in;
  - refresh;
  - cross-organization access;
  - **sign-out refuses the old token immediately**.
- [ ] **ENG:** WP5 role checks on staging, by hand or with the R1 browser spec adapted to staging accounts:
  - warehouse, auditor and manager views;
  - buyer portal and CSV record;
  - Fulfilment Center queues.

## 5. Ministry of Agriculture and FAOSTAT ingestion (offline files)

- [ ] **PO:** request written permission from the Ministry (AMID) to store and analyse its statistics and show derived
  figures with attribution. Record the outcome and conditions.
- [ ] **PO:** confirm FAOSTAT's CC BY 4.0 terms and attribution.
- [ ] **ENG:** load reference data (`agri_import reference`, dry run then `--apply`).
- [ ] **PO/ENG:** verify the FAO item codes for the crops and the FAOSTAT element map against a real download. Only
  then set the `verified` flags, by reviewed change.
- [ ] **ENG:** for each permitted dataset:
  1. register the file (URL, date, SHA-256);
  2. dry run;
  3. review the issues;
  4. `--apply`.

  A second person checks any Ministry PDF transcription.
- [ ] **ENG:** record each source as `APPROVED` only after the PO's licence decision. The importer refuses `--apply`
  until then.
- [ ] Later, with separate authorization: scheduled FAOSTAT retrieval, and a watcher for new Ministry PDF editions
  (`docs/integrations/AGRICULTURAL_DATA.md` §9).

## 6. Messaging (optional, after decisions)

- [ ] **PO:** decide the channel and provider, consent wording and version, data-processing terms, cost limits, and
  whether staging may message real numbers (recommended: test numbers only). See `docs/integrations/MESSAGING.md`.
- [ ] **ENG:** add the provider class and status callback; staging test numbers only. Production stays `none` until
  separately authorized.

## 7. LLM connectivity

- [ ] **PO:** keys for MiniMax or Nebius, in local gitignored files only. Nebius Zero Data Retention switched on.
- [ ] **ENG:** synthetic evaluation of the recovery model (WP3 harness), within an approved budget.
- [ ] **PO:** decide whether evidence-grounded agricultural answers may be used in staging. They are permitted only
  over licence-approved public statistics, with `AGENT_MODEL_STAGING_APPROVAL` recorded and `AGRI_LLM_ENABLED=true`.
- [ ] **ENG:** apply `deploy/sql/agri_readonly_role.sql` if read-only analytics is approved. Build an evaluation set of
  real questions with expected evidence before any real provider run.
- [ ] **ENG, before any real-data model training:** generate forecast lineage from an immutable, content-hashed training snapshot and verify end to end that the model's inputs equal the recorded lineage (debt item 39).
- [ ] Production inference stays disabled until separately authorized.

## 8. Testing on staging

- [ ] Backend suite and R1 browser suite green in CI on the merged branch.
- [ ] `check_staging` all PASS on the deployed system; the staging authentication gate passed.
- [ ] Restore rehearsal on the real project recorded.
- [ ] Uptime alert received in a test.

## 9. Pilot approval (PO)

- [ ] Review `R1_PILOT_READINESS_CHECKLIST.md`, with every blocker closed or explicitly accepted.
- [ ] Pilot organizations, users and data-protection notices confirmed.
- [ ] Release-audit decision, only if a pilot database with real records exists. `--apply` is never run without
  separate approval.
- [ ] Written go-ahead for the pilot.

## Tristan's existing database

Not part of this sequence. It stays untouched until a read-only assessment is separately authorized
(`docs/integrations/LEGACY_DATABASE.md`).
