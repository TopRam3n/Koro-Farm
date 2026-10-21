# Lily meeting — five-minute verified walkthrough

October 20 reliability rehearsal: see `ML_RELIABILITY_HOTFIX.md`. The rebuilt offline preview and regression checks cover cached statistics/FAOSTAT, invalid-artifact handling and the synthetic 500 kg / 80 kg recovery flow. The preserved forecast is unchanged.

Meeting October 20, 2026; stability target October 19. Rehearsal verified October 18 using the production frontend in explicit offline demo mode. National statistics are official cached observations; operational records are synthetic. The model is frozen.

| Time | Screen | Script |
|---|---|---|
| 0:00–0:35 | My Work `/` | “KoroFarm is Agricultural Intelligence & Coordination Infrastructure for the Caribbean. Supply assurance is an operational application.” Follow the Intelligence Lab link. |
| 0:35–1:25 | `/intelligence-lab`, charts and sources | “National Ministry estimates, not farmer stock: 39 validated production quarters and 40 area/price quarters for 2016–2025.” Explain the 2016 Q3 conflict and gap. Show 2025 Q4: 3,110 tonnes, J$1,150.02/kg. |
| 1:25–2:25 | Forecast and backtest panels; expand later evaluation | “Preliminary retrospective evidence: later-window MAE about 554 vs 710 tonnes. These eight quarters were used in release selection; this is not an untouched holdout. Publication vintages are unknown. The 4,069-tonne estimate targets historical 2026 Q1 from a 2025 Q4 cutoff, not today's forecast, a shortage probability or a purchase instruction.” No confidence band is claimed. |
| 2:25–2:50 | Separate FAOSTAT section | “The genuine QCL import has 1,496 Jamaica annual records for 2016–2024. Lettuce/chicory is broader than iceberg. Annual records and source estimates/imputations stay labelled and outside the quarterly model.” |
| 2:50–4:05 | `/requirements/00000000-0000-0000-0000-000000000500` | Show 500 kg committed and 100 kg standby. Simulate an 80 kg dropout, observe 420 kg and 80 kg shortfall, run recovery and observe 500 kg restored. “Commitment is not delivery. This labelled synthetic demonstration does not act on national forecasts.” |
| 4:05–4:35 | `/scenario-lab`, `/traceability` | Point out SIMULATION / No live writes. Optionally set impact to 140 kg. Traceability shows available evidence, not invented delivery proof. |
| 4:35–5:00 | Value Pathways | “Processing, storage and alternative sales are planned economic-value pathways, not an implemented optimizer. Next needs: release vintages, conflict clarification, updated crop statistics and prospective evaluation.” |

From `C:\Users\Lecturer\KoroFarm`:

```powershell
Set-Location src/frontend
$env:NEXT_PUBLIC_APP_MODE='demo'
$env:NEXT_PUBLIC_AUTH_MODE='demo'
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1
```

Open http://127.0.0.1:3000/ . If dependencies are absent, run `npm.cmd ci` with preview stopped before building. This meeting configuration needs no backend database or source website availability. Source/model artifacts are already present; do not rebuild the model for rehearsal.

Use a fresh page/context to reset the in-memory operational demo; it is not persisted across independent contexts. The standalone backend demos separately exercise database-backed domain recovery in isolated synthetic SQLite files. Do not claim deployed multi-tenant readiness, physical delivery from planned coverage, calibrated uncertainty, shortage prediction, or an implemented processing service.
