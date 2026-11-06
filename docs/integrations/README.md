# Integration contracts

Contracts and specifications for everything KoroFarm connects to, or will connect to. Each document separates what
is implemented and tested locally from what has been connected to a real service. As of R1 WP5, **no real external
service is connected** except GitHub Actions CI.

| Document | Covers | Status |
|---|---|---|
| `INGESTION_API.md` | The versioned ingestion boundary for operational observations (secure farmer links, coordinator entry, CSV preview) | Implemented (pre-WP5) |
| `AGRICULTURAL_DATA.md` | Ministry of Agriculture and FAOSTAT statistics: catalogue, licences, templates, normalisation, provenance, validation, future adapters | Prepared; nothing imported |
| `MESSAGING.md` | SMS, WhatsApp and email notifications: consent, templates, statuses, provider contract | Foundation implemented; no provider |
| `ML_AND_LLM.md` | Forecasting interfaces and baselines, backtesting, evidence-grounded answers, privacy and cost controls | Prepared; no provider called |
| `MOA_DATA_PERMISSION_REQUEST.md` | Draft permission request to the Ministry of Agriculture (uses, attribution, derived analytics, optional AI processing, machine-readable data) | Draft for the product owner; not sent |
| `MESSAGING_CONSENT_WORDING.md` | Versioned consent wording for WhatsApp, SMS and email, with channel priorities | Draft for review |
| `LEGACY_DATABASE.md` | Tristan's existing database | Untouched; assessment not started |

**Related:**
- Supabase, hosting, model providers and operations: `docs/product/R1_INFRASTRUCTURE_PLAN.md`,
  `R1_PRODUCT_OWNER_SETUP_GUIDE.md`, `R1_INTEGRATION_READINESS.md`.
- Sequence after WP5: `docs/product/AFTER_WP5_INTEGRATION_CHECKLIST.md`.
- Reviewed SQL: `deploy/sql/`.
- Configuration templates (placeholders only): `deploy/.env.example`, `src/backend/.env.example`,
  `src/frontend/.env.example`.
