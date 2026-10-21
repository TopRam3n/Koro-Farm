# Official Jamaican agricultural statistics

These are public national estimates, not operational inventory or synthetic demonstration data.

- `raw/`: 37 original Ministry PDFs and four acquisition index snapshots.
- `sources.json`: original URLs, SHA-256 hashes, local files, retrieval and HTTP modification metadata.
- `observations.json`: 120 natural-key records; 119 validated cells and one quarantined production cell.
- `quality-report.json`: per-document extraction status, reconciliations, gaps and sanity checks.
- `intelligence.json`: current offline serving artifact.
- `artifacts/<hash>.json`: immutable experiment versions.

2016 Q3 production is intentionally null. The two official sources say 2,525 and 2,998 tonnes. Do not fill this cell without a documented source resolution. Prices and area are not affected by this production-cell dispute.

See `docs/AGRICULTURAL_DATA_SOURCES.md`, `docs/FORECAST_EVALUATION.md` and `docs/AGRICULTURAL_INTELLIGENCE_ARCHITECTURE.md` for source selection, assumptions and reproduction commands.

`faostat/` now contains a genuine Jamaica QCL annual dataset: 1,496 observations for 2016-2024, requested through 2025. Original responses and reviewed API contracts are preserved under `faostat/raw/`. Annual data is separately namespaced, retains source estimates/imputations and original units, and never enters the Ministry quarterly forecast. Reproduce with `python -m src.backend.scripts.acquire_faostat`.
