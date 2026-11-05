# Forecasting and LLM integration specification

**Status:** interfaces, deterministic baselines, backtesting, evidence retrieval and the answer checks are
implemented and tested with **synthetic series and a fake provider client**.
- No model has been trained on paid infrastructure.
- No model has been fine-tuned.
- No real provider has been called.

The deterministic recovery engine is unchanged, and so are human approval, consent, stock conservation and execution
safeguards. Forecasts and answers are advisory analytics; they never move stock, commit suppliers or skip approval.

## Forecasting (`src/backend/app/agriculture/forecasting.py`)

| Piece | Contract |
|---|---|
| `Forecaster` | `fit(values)` on one ordered, equally spaced series; `predict(horizon)` returns points with an empirical interval (default 80%). Forecasts are never negative |
| Baselines | `last_value`, `seasonal_last_value` (season 4 for quarters), `moving_average`, `drift`. Every later model must beat these in a backtest before it is used |
| `build_features` | Lags 1–3, a 3-period rolling mean and standard deviation, and period-over-period change, all from **earlier periods only** (no look-ahead). Missing history is `None`, never imputed |
| `backtest` | Rolling origin: at each origin, fit on everything before it and score the forecast. Reports MAE, RMSE, sMAPE, MASE (against the last-value error) and interval coverage |
| `record_model_run` | Stores the run (model, version, parameters, training window, data snapshot of observation ids), forecasts and metrics in `agri.model_runs`, `agri.forecasts` and `agri.model_evaluations` |

**Next steps, after real data is licensed and imported:**
1. Run the baselines per crop and measure, and publish their backtest metrics.
2. Try statistical models (for example exponential smoothing) as new `Forecaster` classes, locally, at no cost.
3. Consider machine-learning models on `feature_values` only if they beat the baselines with enough history. Annual
   series of about 10 points are too short for most of them.

## Evidence-grounded answers (`src/backend/app/agriculture/evidence.py`)

1. **Retrieval:**
   - Only named, parameterised queries over `agri` (`QUERY_CATALOGUE`), with codes and years validated. A model
     never writes SQL.
   - Each query runs on a dedicated connection in a `READ ONLY` transaction, with a 5-second timeout and at most 500
     rows. Operational tables are never read.
2. **Evidence:** each fact carries its source, dataset, publication, retrieval time, revision, licence status and
   attribution.
3. **Gate** (`provider_permitted`). Every condition must hold:
   - The existing model gate allows it: never in production; staging only with the recorded approval reference.
   - `AGRI_LLM_ENABLED=true`.
   - Every fact comes from a source whose licence is `APPROVED`.
   - Every fact is classified `PUBLIC_STATISTICS`; operational data never goes to a provider.
   - The request is within `AGRI_LLM_MAX_INPUT_TOKENS` (default 6000).

   Otherwise a deterministic summary of the evidence is returned, with the reason, and nothing is sent.
4. **Answer check:**
   - The model must return JSON (`ANSWER_SCHEMA`) and cite evidence ids that exist.
   - Every figure it states must equal a cited fact. Years are allowed.
   - Any failure discards the answer for the deterministic summary.
5. **Provider:** the existing adapters (`agents/infrastructure/providers.py`: MiniMax, Nebius; Anthropic disabled)
   are reused through their `complete(system, user, schema)` interface. After an error there is no switching to
   another paid provider.

## Privacy and cost controls

- **Data:** only public statistics, and only from licence-approved sources. Nebius Zero Data Retention is required
  before any call. MiniMax: synthetic data only, unless a data agreement exists (infrastructure plan).
- **Cost:** input budget per request. An evaluation run against a real provider needs the product owner's approval
  of the budget first, as for the recovery model.
- **Logging:** model reasoning is never stored, and keys never appear in logs (`scrub`).

## Synthetic evaluation fixtures

These tests demonstrate the controls with synthetic data:
- `tests/test_agri_intelligence.py`:
  - deterministic baselines and non-negative intervals;
  - features without look-ahead;
  - the seasonal baseline wins on seasonal data;
  - grounded answers accepted, while invented figures, unknown citations and uncited numbers are rejected;
  - every gate refuses when it should, and no call is made.
- `tests/test_agriculture_postgres.py`: read-only evidence queries and stored model runs.

**Before any real provider evaluation:** an evaluation set of real questions with expected evidence (`build-eval`
style), approved by the product owner.
