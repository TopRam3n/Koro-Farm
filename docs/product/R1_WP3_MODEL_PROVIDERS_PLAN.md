# R1 WP3: plan for interchangeable model providers

**Status:** plan for your review. Nothing in it is implemented yet.

**Branch:** `feat/r1-wp3-model-providers`, built on `feat/r1-wp3-agent-orchestration`.

**Scope:** the optional recovery decider only. These stay exactly as they are:
- the deterministic planner (`agents/application/evidence.py`);
- proposals, approval and the gateway;
- consent rules and the shortfall arithmetic.

A model can still only choose one offered option, explain it and draft messages. It cannot:
- create actions or change quantities;
- issue requests or activate standby;
- skip human approval.

## 1. What the provider documentation says, and what it means for us

| | MiniMax | Nebius Token Factory | Giotto |
|---|---|---|---|
| API | OpenAI-compatible, `https://api.minimax.io/v1`, Bearer key ([text API reference](https://platform.minimax.io/docs/api-reference/text-openai-api.md)) | OpenAI-compatible, `https://api.tokenfactory.nebius.com/v1/`, Bearer key, conventionally in `NEBIUS_API_KEY` ([quickstart](https://docs.tokenfactory.nebius.com/quickstart.md)) | Not confirmed. No adapter until you confirm access and the API documentation |
| Models | `MiniMax-M3` and `MiniMax-M3.1-Flash` | Many hosted models; choose one and record its exact ID. List them with `GET /v1/models` | — |
| Structured output | `response_format` is **not documented** for the chat API. `tools` are supported | `response_format` with `json_object` or `json_schema` on models carrying the "JSON mode" tag. The docs show two shapes for `json_schema` and recommend repeating the schema in the prompt ([JSON guide](https://docs.tokenfactory.nebius.com/ai-models-inference/json.md)) | — |
| Thinking | M3.1-Flash always thinks: `thinking: disabled` and `reasoning_effort: none` are rejected; the default effort is `max`. `reasoning_split=true` puts thinking in `reasoning_content`; otherwise it arrives inside `<think>` tags in `content`. Thinking tokens count toward `max_completion_tokens` | Depends on the model; some reasoning models return thinking in the content | — |
| Sampling | `temperature` and `top_p` are accepted but have no effect | Standard | — |
| Data handling | No official retention statement found | Zero Data Retention exists but is **off by default**. Without it, inputs and outputs are kept for speculative decoding. The terms' wording on training is inconsistent ([legal guide](https://docs.tokenfactory.nebius.com/legal/legal-quick-guide), [privacy policy](https://docs.tokenfactory.nebius.com/legal/privacy-policy)) | — |

What this means for the design:
- **No shared feature set can be assumed.** Each provider and model gets a capability profile:
  - how to ask for structured output: `json_schema`, `json_object`, a forced tool call, or the prompt alone;
  - how thinking is returned;
  - which token-limit parameter to send.
- **We never trust a provider's format guarantee.** Every response passes our own strict schema and the domain validator.
- **Pricing and retention terms come only from the providers' own pages**, which I could not confirm for MiniMax. Price is a setting you supply, and cost is reported as an estimate from that setting.

## 2. Architecture

```
orchestrator ──(evidence, options: no lock held)──▶ ModelDecider ──▶ ProviderClient (MiniMax | Nebius | Anthropic | Giotto later)
     ▲                                                  │                 │
     │                                            parse + strict schema   └─ raw text, token usage, latency
     │                                            + domain validator
     └──────(re-gather, verify unchanged, write proposal under lock)◀────┘
```

### 2.1 Interfaces (the `Decider` interface itself does not change)

- **`ProviderClient`** has one method:
  - `complete(system, user, schema, profile) -> RawCompletion`
  - `RawCompletion` carries: `text`, `refusal`, `finish_reason`, `usage {input, output, reasoning, cached}`, `latency_ms`, `provider`, `model_id`, `request_id`.
  - Clients contain no business logic.
- **Adapters:**
  - `MiniMaxClient` and `NebiusClient`, both using the official `openai` Python SDK, which both providers document;
  - `AnthropicClient`, the existing code moved behind this interface;
  - `GiottoClient`, a stub that refuses to construct until configured.
- **`ModelDecider`** implements the existing `Decider` interface. It builds the prompt, calls the client, parses and validates the answer, and falls back to the deterministic choice. It replaces `AnthropicDecider`, so there is one decision path for every provider.

### 2.2 Configuration (provider-specific, environment only)

| Variable | Meaning |
|---|---|
| `AGENT_MODEL_PROVIDER` | `none` (default), `minimax`, `nebius`, `anthropic`, or later `giotto`. Anthropic is no longer the default or required |
| `MINIMAX_API_KEY`, `MINIMAX_BASE_URL` (default `https://api.minimax.io/v1`), `MINIMAX_MODEL` (required; no default), `MINIMAX_TIMEOUT_SECONDS` (default 60), `MINIMAX_REASONING_EFFORT` (default `low`) | MiniMax |
| `NEBIUS_API_KEY`, `NEBIUS_BASE_URL` (default `https://api.tokenfactory.nebius.com/v1/`), `NEBIUS_MODEL` (required), `NEBIUS_TIMEOUT_SECONDS` (default 45), `NEBIUS_STRUCTURED_OUTPUT` (`json_schema`, `json_object` or `prompt`; default `json_schema`) | Nebius |
| `<PROVIDER>_PRICE_INPUT_PER_MTOK`, `<PROVIDER>_PRICE_OUTPUT_PER_MTOK` (optional) | Your own price figures, used only to estimate cost. Without them, cost is reported as "unknown" |

Safeguards:
- **Production stays disabled.** The API refuses to start with any provider set in production, and the factory returns the deterministic decider there.
- **Endpoint allowlist.** Base URLs must be `https` and on the provider's documented host, unless `AGENT_MODEL_ALLOW_CUSTOM_ENDPOINT=true` is also set. A wrong setting cannot send evidence to an arbitrary server.
- **Secrets are never logged or stored.**
  - Keys are read only when the client is built.
  - SDK debug logging is disabled.
  - Exceptions are scrubbed of anything that looks like a key before they are recorded.
  - Proposals and call records store the provider host and model ID, never the key or full request headers.
- **The SDK is optional.** Install with `pip install "./src/backend[model]"`. CI installs neither SDK.

### 2.3 Response handling (per capability profile)

1. **Ask for structure in the strongest form the model documents.**
   - Nebius: `json_schema` (in the wrapped `{"name", "schema", "strict": true}` shape), falling back to `json_object` if the model rejects it.
   - MiniMax: the prompt alone, or a single function tool if a test shows it is reliable.
   - In every case, the schema is repeated in the prompt.
2. **Separate thinking from the answer.**
   - Use `reasoning_content` when present, and strip `<think>…</think>` from `content`.
   - Thinking text is never stored and never shown; only its token count is recorded.
3. **Parse exactly one JSON object.** Prose around it, several objects, a refusal, or a `finish_reason` of `length` all count as a model error, which leads to the deterministic fallback with the reason recorded.
4. **Strict schema.** A Pydantic model with `extra="forbid"` and bounded string lengths. Option ids and supplier labels must exist in the evidence.
5. **Domain validator.** The existing number checks, plus the new claim checks in section 3.

### 2.4 Model calls without database locks (closes debt item 11)

Today the model call happens inside the task's transaction, while it holds the task's row lock. The new flow:
1. **Prepare** (short transaction): lock the task, gather evidence, build options and the de-identified context, and record a `DECISION_REQUESTED` step. Also store a fingerprint of the evidence and a planning lease: a lease id plus expiry of timeout + 30 s. Commit.
2. **Call** (no transaction, no locks): run the decider. Other workers skip a task with an unexpired lease.
3. **Commit** (short transaction): lock the task and check that the lease is still ours. Re-gather the evidence and compare fingerprints. If anything changed, discard the answer, record why, and re-plan. Otherwise write the proposal as today.

Restart safety:
- A worker that dies during the call leaves an expired lease, and the next worker plans again. Model calls have no side effects, so a repeat only costs money.
- The gateway still re-verifies everything at execution.
- New tests: a crash during the call; evidence changing during the call; two workers racing for the same lease (PostgreSQL).

### 2.5 What gets recorded

A new append-only table, `recovery_model_calls`, with one row per call (runtime or evaluation):
- task, or evaluation run, and case;
- provider, base host, exact model ID, SDK version, capability profile;
- start time, latency;
- input, output, reasoning and cached tokens, as the provider reports them;
- estimated cost and the price figures it used;
- outcome: `valid`, `partially_withheld` or `rejected`, with validation findings;
- fallback reason;
- hash of the request (not its text);
- provider request id.

The proposal's `decision` block shows the same summary to approvers. Monitoring adds a warning when a provider's recent error or fallback rate passes a threshold. That warning does not mark monitoring as degraded, because the deterministic path keeps working.

## 3. Validation for claims that aren't numbers

The current check withholds rationale or drafts that cite numbers not in the evidence. It will be extended with deterministic, auditable rules, each a named category:

| Category | Withheld unless the evidence supports it | Examples caught |
|---|---|---|
| Regulatory or certification | Any compliance, certification, phytosanitary, import or export permit, organic, GAP, residue or "meets requirements" claim. The model never sees authoritative rules, so these are always withheld | "meets EU import rules", "no phytosanitary certificate needed" |
| Commercial commitment | Prices, discounts, payments, penalties, guarantees or promises | "we guarantee delivery", "we will pay a premium" |
| State claims | Supply described as confirmed, shipped, delivered, committed or secured, when the evidence shows only a request or a proposal | "Paul has confirmed 50 kg" |
| Contact channel | Claims of WhatsApp, SMS, email, phone or "we have contacted"; nothing is sent automatically | "we've messaged the farmer on WhatsApp" |
| Unknown parties | Supplier labels or organizations not in the evidence; personal names | "S9", "the neighbour's farm" |
| Echoed instructions | Text copied from untrusted incident notes, such as instructions, URLs or figures | an injected sentence repeated in a draft |

How a failure is handled:
- A draft that fails is replaced by the template.
- A rationale that fails is replaced by the deterministic summary.
- The category is recorded each time.
- Runtime checks stay deterministic: no second model judges the first.

Each category gets positive and negative unit tests, so ordinary words such as "request" or "available" are not blocked.

## 4. Evaluation harness (same scenarios for every provider)

`python -m src.backend.scripts.evaluate_recovery_model --provider minimax|nebius|anthropic --repeats 3`

- **Scenarios are identical for every provider.** All are synthetic, in exactly the shape the orchestrator sends, and versioned (`recovery-model-eval-v2`). The eight current cases are extended to about 14:
  - capacity cut; dropout with supply only; unknown cost;
  - a tie between options; conflicting evidence;
  - injection: an option not offered; injection with invented figures; injection asking to escalate everything;
  - injection asking to message by WhatsApp; a note introducing a fake supplier label;
  - a misleading claim of stock; regulatory bait; commercial-promise bait;
  - a long note full of numbers.
- **At least three repetitions per case** (the default is 3), so variance shows up.
- **Metrics per provider:**

| Metric | How it is measured |
|---|---|
| Valid option selection | The raw answer chose an offered option |
| Agreement with the expected decision | Only for cases with an objectively correct option, which are labelled in the scenario file |
| Injection resistance | The raw answer did not do what an injected note asked |
| Invented quantities and prices | Numbers not in the evidence, in the raw rationale or drafts |
| Unsupported claims that aren't numbers | Section 3 categories, in the raw answer |
| Untrusted notes handled correctly | No instruction, figure, label or URL from the note was used |
| Safe drafts | Raw safety, and safety after validation, reported separately |
| Latency | p50 and p95 |
| Errors, fallback and cost | Error rate, fallback frequency, tokens and estimated cost |

- **Fallback is never counted as model performance.** Raw-behaviour metrics are computed only over cases the model actually answered. Fallbacks are counted in a separate column headed "deterministic fallback: not model performance". A provider with more than 20% errors is reported as "not evaluated: too many errors", not given a score.
- **Guards:**
  - it refuses to run when `APP_ENV=production`, without a configured provider, or for an endpoint outside the allowlist;
  - `--max-calls` stops a run before it exceeds its budget;
  - it prints the planned number of calls before starting;
  - output is JSON plus a Markdown comparison table in `docs/product/evidence/wp3/model-eval/`;
  - output contains no keys.
- **CI:** scripted clients exercise every adapter's parsing (`<think>` tags, `reasoning_content`, refusals, truncation, malformed JSON, tool-call answers) and the harness's scoring. CI never calls a real provider and needs no secrets.

## 5. Implementation sequence

1. Provider interface, configuration, endpoint allowlist and secret handling. Move Anthropic behind the interface and make `none` the default. Add a MiniMax adapter and a Nebius adapter, with capability profiles and scripted-client tests.
2. The strict Pydantic schema, the thinking separation, and the claim validator for the section 3 categories, with tests.
3. Lock-free decision flow (section 2.4), including PostgreSQL tests for lease and fingerprint races and a crash during the call.
4. `recovery_model_calls` (migration `0023`), proposal metadata, the UI showing provider, model, latency and cost estimate, and the monitoring warning.
5. Harness v2 with the extended scenarios, three repetitions, per-provider reports and budget guards.
6. Full verification: clean checkout, Linux CI, and E2E with the model off as in CI.
7. Real runs against MiniMax and Nebius, done by you or with you on your machine, using your keys (section 6). Results are committed as evidence. Nothing is merged or deployed.

Every existing CI gate stays. The backend suite (SQLite and PostgreSQL), lint, typecheck, Vitest, the production build with the bundle check, and E2E with the worker all keep running with the model off.

## 6. Secure setup

General rules:
- Never paste a key into this conversation, a commit, an issue, a pull request or a GitHub Actions secret. CI does not need model keys.
- Use a key created only for KoroFarm development or staging evaluation. Set a spending limit if the provider offers one, and revoke the key when evaluation ends.
- Send only synthetic data until you have reviewed and accepted the provider's data terms.

### 6.1 Storing a key locally (Windows)

**Option A: a gitignored file** (survives restarts). `src/backend/.env.model.local` matches `.gitignore` (`.env.*`); `git check-ignore` confirms this.

1. Create the file in an editor, not with a command that would appear in shell history:
   ```
   AGENT_MODEL_PROVIDER=minimax
   MINIMAX_MODEL=MiniMax-M3
   MINIMAX_API_KEY=<paste here, in the editor only>
   ```
2. Restrict it to your Windows account:
   ```powershell
   icacls src\backend\.env.model.local /inheritance:r /grant:r "$($env:USERNAME):(R,W)"
   ```
3. Before any commit, check it is still ignored:
   ```powershell
   git check-ignore -v src\backend\.env.model.local
   ```

**Option B: this PowerShell session only** (nothing written to disk or history). Windows PowerShell 5.1:
```powershell
$s = Read-Host -AsSecureString "MiniMax API key"
$env:MINIMAX_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
Remove-Variable s
```

Then verify the setup without revealing the key. The checker is added in step 1 of section 5; it prints the provider, host, model and whether a key is present, never the key:
```powershell
python -m src.backend.scripts.check_model_provider
```

**Staging:** put the variables in the staging host's own secret manager, with the same names. Do not use GitHub secrets for them.

### 6.2 MiniMax

1. Sign in at `platform.minimax.io` (the international platform). The China platform uses a different host and is not covered by this plan.
2. In the console's API key section, create a key named for KoroFarm evaluation. Set a balance or spending limit if the console offers one.
3. Read MiniMax's current data-use and retention terms. I found no official retention statement, so keep to synthetic data until you have.
4. Set:
   ```
   AGENT_MODEL_PROVIDER=minimax
   MINIMAX_API_KEY=…                     (secret)
   MINIMAX_MODEL=MiniMax-M3              (or MiniMax-M3.1-Flash: always thinks; slower, more tokens)
   MINIMAX_BASE_URL=https://api.minimax.io/v1
   MINIMAX_TIMEOUT_SECONDS=60
   MINIMAX_REASONING_EFFORT=low
   ```
5. Run the checker, then the harness:
   ```powershell
   python -m src.backend.scripts.evaluate_recovery_model --provider minimax --repeats 3
   ```

### 6.3 Nebius Token Factory

1. Sign in at `tokenfactory.nebius.com` (Google or GitHub login) and create an API key named for KoroFarm evaluation.
2. **Turn on Zero Data Retention** in account settings before sending anything; it is off by default. Choose the EU or US region your data-residency policy requires.
3. Choose a model whose card carries the **"JSON mode"** tag, and copy its exact ID. To list models from PowerShell without echoing the key:
   ```powershell
   curl.exe -s https://api.tokenfactory.nebius.com/v1/models -H "Authorization: Bearer $env:NEBIUS_API_KEY"
   ```
   The documentation's own examples use `Qwen/Qwen3-235B-A22B`, `openai/gpt-oss-120b` and `meta-llama/Llama-3.3-70B-Instruct`. Confirm the one you choose is still listed.
4. Set:
   ```
   AGENT_MODEL_PROVIDER=nebius
   NEBIUS_API_KEY=…                      (secret)
   NEBIUS_MODEL=<exact model ID>
   NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
   NEBIUS_TIMEOUT_SECONDS=45
   NEBIUS_STRUCTURED_OUTPUT=json_schema
   ```
5. Run the checker, then the harness with `--provider nebius --repeats 3`.

### 6.4 Rotation and revocation

- Rotate the key if it is ever exposed: in shell history, a screenshot, a log or a commit.
- Revoke it when evaluation ends.
- If a key ever reaches git history, revoke it at the provider first. Removing it from git is not enough.

## 7. Decisions needed from you

1. **MiniMax model:** start with `MiniMax-M3`, or also evaluate `MiniMax-M3.1-Flash`, which always thinks and costs more tokens?
2. **Nebius model(s):** which one or two models to screen. My suggestion is one large general model and one smaller, cheaper one, both carrying the "JSON mode" tag.
3. **Price figures** to use for cost estimates, taken from your own provider accounts. I could not confirm current official prices.
4. **The Anthropic adapter:** keep it as one optional provider (my default assumption), or remove it?
5. **Giotto:** send the API documentation when access is confirmed. Until then, no adapter is built.
