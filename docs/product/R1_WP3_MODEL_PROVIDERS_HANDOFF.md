# R1 WP3: model providers handoff

**Branch:** `feat/r1-wp3-model-providers`, built on `feat/r1-wp3-agent-orchestration`. Pushed to `origin`. Not merged; nothing deployed.

**Code verified:** `db6a24f57483de225b8f0396e96c2312b110df90`. The commit that adds this document contains documentation only.

**CI:** **green** on `db6a24f`: run [41263452498](https://github.com/TopRam3n/Koro-Farm/actions/runs/41263452498), job `verify`, every step passed.

**Approved plan:** [R1_WP3_MODEL_PROVIDERS_PLAN.md](R1_WP3_MODEL_PROVIDERS_PLAN.md), with your decisions of 31 October 2026. The secure setup steps are in its section 6.

## What was built

| Your requirement | Implementation |
|---|---|
| Interchangeable providers; the `Decider` interface and deterministic fallback preserved | `ModelDecider` (`agents/infrastructure/model.py`) runs one decision path over a `ProviderClient` (`providers.py`). The planner, proposals, approval, gateway and consent rules are unchanged |
| MiniMax: `MiniMax-M3` and `MiniMax-M3.1-Flash` | Uses the OpenAI-compatible SDK MiniMax documents. Sends `reasoning_split=true`. For M3.1-Flash, `reasoning_effort` comes from `MINIMAX_REASONING_EFFORT`, `low` by default. No `response_format`, which MiniMax does not document; the schema goes in the prompt. Temperature is not sent, because MiniMax ignores it |
| Nebius: `Qwen/Qwen3-30B-A3B-Instruct-2507` and `Qwen/Qwen3.5-397B-A17B` | Strict `json_schema` first, then the documented fallbacks on **the same model**: `json_object`, then the prompt alone. The mode used and any rejected mode are recorded. **Not yet checked: whether both models are offered to your account and which JSON modes each accepts.** That needs your key. `check_model_provider` and the harness check both: the account's model list, then the calls |
| Anthropic optional and off by default; never required | `AGENT_MODEL_PROVIDER` defaults to `none`. The Anthropic SDK is a separate `[anthropic]` extra, imported only when that provider is selected. The clean checkout ran with neither SDK installed |
| Never switch paid providers after an error | Exactly one provider is configured. Any error leads to the deterministic fallback, with the reason recorded. Tests assert that every request in a failure goes to one model |
| Giotto deferred | No adapter. `AGENT_MODEL_PROVIDER=giotto` is refused as an unknown provider |
| Provider-specific configuration; secrets only in the environment | `<PROVIDER>_API_KEY`, `_MODEL` (required), `_BASE_URL` and `_TIMEOUT_SECONDS`. Base URLs must be https on the documented host. Keys never appear in `repr`, logs, stored errors, proposals, call records or reports: `scrub()` is applied, and SDK debug logging is off. Tests check each of these |
| Our own strict schema and domain validator on every response | `parse_answer` accepts exactly one JSON object matching `DecisionAnswer` (strict types, no extra fields, bounded lengths). Then come the offered-option check, the number check, and claims that aren't numbers |
| Claims that aren't numbers | `claim_findings` checks six categories: regulatory or certification, commercial commitment, state ("confirmed", "shipped"), contact channel (WhatsApp, SMS, email, "we contacted"), unknown supplier labels, and text, links or figures echoed from untrusted incident notes. A failing rationale, draft or information request is withheld and the category recorded |
| Recording provider, model, latency, tokens, cost, validation and fallback reason | Each call writes a `recovery_model_calls` row (migration `0023`), and the proposal's decision block shows the same to approvers. Outcomes are `valid`, `partially_withheld`, `fallback` or `discarded`. Model reasoning is never stored: it is split out or stripped, and only reasoning-token counts are kept |
| Versioned, model-specific pricing | `pricing.py`, version `list-prices-2026-10-31`. Covers your four rates, MiniMax-M3's over-512K tier and Priority tier, and the published cache-read rates. Nebius publishes no cached-input rate, so cached input is charged as input, and the estimate says so. Every estimate is labelled "estimate, not an account charge" |
| No database locks held during model calls; restart safety; revalidation | Prepare, then call, then commit (`orchestrator.advance_due` and `finish_decision`):<br>1. Record a planning lease and an evidence fingerprint, and commit.<br>2. Call the model with no transaction open.<br>3. Re-lock the task and use the answer only if the lease is still ours and the fingerprint is unchanged; otherwise discard it, record the call, and re-plan.<br>The gateway still re-verifies everything at execution |
| Production disabled | Startup refuses any provider except `none` in production, and `build_decider` returns the deterministic decider there |
| Monitoring | `/system/status` reports calls, fallbacks, latency and estimated cost per model over 24 hours, and a `model_fallbacks_high` warning. This is a warning only: deterministic recovery keeps working |
| Harness: identical scenarios, ≥3 repetitions, USD budget and call cap | `evaluate_recovery_model.py` v2:<br>• 14 synthetic cases: 5 ordinary, 5 injection, 2 misleading, 2 bait. Default `--repeats 3`.<br>• `--max-usd` (default 2.00) and `--max-calls` (default 250) are enforced during the run, from estimated spend.<br>• Each target ends as evaluated, unavailable, not run (no key), or not evaluated (more than 20% errors).<br>• Raw measures use answered calls only; fallbacks are counted separately and never as model performance.<br>• Output is JSON and Markdown, with no keys |

Two more changes:
- **Key checker:** `check_model_provider` prints the provider, host, model, whether a key is present (never the key), whether the model is offered to the account, and the result of one synthetic call.
- **Date-boundary defect fixed.** `authorized_standby()` judged standby validity by the local date, while expiry, response checks and the gateway used the UTC date. It now uses UTC everywhere. Two WP2 tests built dates the same local way and failed between 19:00 local time and midnight UTC; they now use the API's UTC day. This is item 15 in the debt register.

## Clean-checkout verification of `db6a24f`

Method:
- a new worktree (0 dirty files, no `.env` files);
- a new venv with `[dev]` only, so **neither `openai` nor `anthropic` was installed** (checked inside the venv);
- `npm ci`;
- the disposable PostgreSQL 17 instance;
- a fresh E2E database migrated to `0023`.

| Gate | Result |
|---|---|
| Backend, SQLite and PostgreSQL | **404 passed, 0 skipped** |
| `tsc` / `eslint .` | exit 0 / exit 0 |
| Vitest | **44 passed** |
| Production build plus `check:bundle` | exit 0; 966 files, no test-auth material |
| Browser E2E with the worker running (model off, as in CI) | **21 passed** |

The only tracked file changed was the regenerated `src/frontend/next-env.d.ts`. The worktree was then removed.

## Test results reconciled

| Run | Commit | Backend | Vitest | E2E |
|---|---|---|---|---|
| Clean checkout, WP3 final | `bb173d9` | 363 | 44 | 21 |
| Local working tree | before `db6a24f` | 404 | 44 | not run separately |
| Clean checkout | `db6a24f` | 404 | 44 | 21 |
| CI 41263452498 | `db6a24f` | pass | pass | pass |

**Backend +41:**
- `test_recovery_model.py` was rewritten around a scripted OpenAI-compatible SDK. It now runs 30 SQLite and 29 PostgreSQL cases, up from 21. It covers:
  - provider request shapes and reasoning separation;
  - the JSON-mode fallback and failure kinds;
  - strict parsing and the claim categories, positive and negative;
  - de-identification, injection, and the lock-free lease flow (crash during the call, evidence change, lease takeover);
  - the endpoint allowlist, secret scrubbing, pricing, the production lock, monitoring and the harness.
- `test_postgres_integration.py`: a race of two workers for one lease, which produced one model call and one proposal.

**Faults found during this work, all fixed:**
- Reused scripted clients made the PostgreSQL runs see already-consumed errors.
- Three of my own pricing assertions used the wrong tier.
- One test changed nothing during the model call.
- The date-boundary defect above.

No test was skipped or retried in the runs listed.

## Live synthetic evaluation: not yet run

On 31 October and 1 November 2026, no `MINIMAX_API_KEY` or `NEBIUS_API_KEY` was configured on this machine, and none was requested in conversation. So there are **no live results, and no availability or JSON-mode check against your account**. Nothing in this handoff should be read as evidence about how any model performs.

To run it, after the steps in plan section 6:
```powershell
python -m src.backend.scripts.check_model_provider --provider minimax --model MiniMax-M3
python -m src.backend.scripts.check_model_provider --provider nebius --model Qwen/Qwen3-30B-A3B-Instruct-2507
python -m src.backend.scripts.evaluate_recovery_model --repeats 3 --max-usd 2
```
The harness writes `docs/product/evidence/wp3/model-eval/recovery-model-eval-<time>.json` and `.md`. Its rough pre-run estimate for 4 targets × 14 cases × 3 repeats (168 calls) is printed before it starts.

## Conditions before any use beyond synthetic data

| Item | Status |
|---|---|
| Nebius Zero Data Retention switched on and confirmed | **Required, not done.** It is off by default at Nebius |
| MiniMax privacy and data-handling review | **Required, not done.** I found no official retention statement |
| Live synthetic evaluation of all four models | Waiting for keys configured locally |
| Production model access | Disabled until you authorize it separately |
| Earlier gates: staging Supabase verification; merging WP1, then WP2, then WP3, then this branch; the supervised worker | Unchanged; see the WP2 and WP3 handoffs |
