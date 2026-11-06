# Agricultural data integration specification

**Status:** PREPARED. Schema (migration 0029), offline importer, reference files and templates exist and are tested on
PostgreSQL with synthetic data. **No Ministry or FAOSTAT data has been retrieved or imported.**
No live connection exists, and none is needed for the first imports.

**Updated:** 5 November 2026 (R1 WP5).

## 1. Principles

- **Separate from trade data.** Statistics live in the PostgreSQL schema `agri`, never in the operational `public`
  tables, and nothing in `agri` is granted to Supabase's client roles or to `PUBLIC`.
- **Nothing is invented.** No statistic is entered by a migration or seeded. A figure enters only from a retrieved,
  registered file, with its provenance.
- **Licence first.** An import can be applied only when the source's licence review is `APPROVED`. Dry runs are
  always allowed.
- **Never overwritten.**
  - A changed figure becomes a new revision.
  - The old figure stays, marked not current.
  - Every source row is kept as read.
- **Idempotent.**
  - A file is identified by its SHA-256.
  - Importing the same file again changes nothing and reports `ALREADY_IMPORTED`.
- **Tristan's existing database is untouched.** It is a separate legacy source. See `LEGACY_DATABASE.md`.

## 2. Source catalogue

Reference copy: `src/backend/data/agriculture/reference/sources.csv` and `datasets.csv`.

| Source | Datasets | What was found (5 November 2026) | Licence review |
|---|---|---|---|
| **Ministry of Agriculture, Fisheries and Mining, Jamaica**, Agricultural Marketing Information Division (AMID). Index: https://www.moa.gov.jm/content/agricultural-data | 11 listed. Prepared: area reaped (10-year and quarterly); production (10-year and quarterly); farmgate prices (10-year and quarterly); and "Area Reaped Production And Farmgate Prices" (yearly). | Pages link to **PDF files only**, with no CSV or Excel:<br>• the 10-year area-reaped page lists editions from 2007-2016 to 2016-2025;<br>• the yearly page lists 2014 to 2025, with no 2017 or 2018 file seen.<br>The pages state no units, column definitions or revision notes; these must be read from the PDFs. | **PERMISSION_REQUIRED.** The footer reads "Copyright © 2020. Government of Jamaica. All Rights Reserved." No reuse licence was found. Contact: psecoffice@moa.gov.jm |
| **FAOSTAT** (FAO). https://www.fao.org/faostat/en/ | QCL (crops and livestock products: area harvested, production, yield); PP (producer prices) | Bulk normalized CSV downloads | **NOT_REVIEWED.** FAO's database terms say its statistical databases are under **CC BY 4.0** from 1 July 2024, unless a dataset's metadata says otherwise, with additional terms of use. Required citation: "FAO. [year]. [dataset]. FAOSTAT. Accessed [date]. [URL]. Licence: CC-BY-4.0." Product owner to confirm |

**Datasets not prepared:**
- the Ministry's livestock dataset;
- the three export-crop datasets.

They are outside the crop scope and are listed in the index for completeness.

## 3. How data enters (first imports are manual and offline)

1. **Retrieve.** A person downloads the file from the official page and records:
   - the URL, date, edition and file name;
   - the SHA-256 (`publication_register_template.csv`).
2. **Transcribe** (Ministry PDFs only). Copy the table into `observations_template.csv`:
   - exactly as published, one figure per row;
   - with `source_row_reference` pointing to the page and row.

   A second person checks the transcription against the PDF. Automated PDF extraction is a later option (§9).
3. **Dry run.**

   ```text
   python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.agri_import observations FILE.csv
   ```

   It reports rows read, accepted, rejected and duplicate, plus every validation issue. Nothing is written.
4. **Apply** with `--apply`, once the licence is `APPROVED` and the dry run is clean.
5. **FAOSTAT.** Import the downloaded normalized CSV directly:

   ```text
   agri_import faostat FILE.csv --dataset QCL
   ```

   Every row is kept with FAO's own codes and flags (`faostat_observations`). A row becomes a KoroFarm observation
   only when both of these are true:
   - its element is in a **verified** element map;
   - its item maps to a crop whose FAO item code is **verified**.

## 4. Templates

Folder: `src/backend/data/agriculture/templates/`.

| File | Columns |
|---|---|
| `observations_template.csv` | `source_code, dataset_code, crop, geography, measure, period_type, period, value, unit, status, quality_flag, source_row_reference, notes`. One dataset per file |
| `publication_register_template.csv` | `source_code, dataset_code, version_label, period_label, published_on, retrieval_url, file_name, content_sha256, retrieved_at, retrieved_by, notes` |
| `crop_alias_template.csv`, `geo_alias_template.csv` | `crop_code` or `geo_code`, `alias`, `source_code` (empty: applies to every source) |

**Values:**

| Field | Format |
|---|---|
| `period_type` | `YEAR` (`2024`), `QUARTER` (`2024-Q1`) or `MONTH` (`2024-03`) |
| `status` | `PROVISIONAL`, `REVISED`, `FINAL` or `ESTIMATE` |
| `value` | As published: thousands separators allowed; no negative numbers |

## 5. Normalisation

- **Names.**
  - Crops and places match through reviewed aliases.
  - The matching key ignores case, punctuation and "Saint"/"St.", so "St. Ann", "Saint Ann" and "ST ANN" are the same.
  - Every canonical name is its own alias.
  - An unmapped name is **rejected**, never guessed. To fix it, add an alias row, reviewed.
- **Crops** (`crops.csv`).
  - The ten operational crops, with matching `operational_crop_code`.
  - FAO item codes are best-knowledge values marked `fao_item_code_verified=false`. They must be checked against
    the FAOSTAT item list before mapping:

    | Crop | FAO item code |
    |---|---|
    | Banana | 486 |
    | Plantain | 489 |
    | Cassava | 125 |
    | Ginger | 720 |
    | Mango | 571 |
    | Sweet potato | 122 |
    | Yam | 137 |

  - Breadfruit, callaloo and scotch bonnet have no FAO item code set. Scotch bonnet would fall under the broader
    "chillies and peppers"; that is a judgement for the product owner, not a mapping to apply silently.
- **Places** (`geo_areas.csv`).
  - Jamaica: ISO JM, M49 388, FAO area code 109 (verify).
  - The 14 parishes, ISO 3166-2 JM-01 to JM-14.
- **Units** (`units.csv`). Each figure keeps its published unit, plus a canonical value:

  | Quantity | Canonical unit | Converted from |
  |---|---|---|
  | Area | ha | acres |
  | Mass | tonne | kg, lb |
  | Yield | kg/ha | t/ha, hg/ha |
  | Price | J$/kg | J$/lb, J$/t |

  **US dollars are never converted to Jamaican dollars**: no exchange rate is applied.
- **Measures** (`measures.csv`):

  | Measure | Note |
  |---|---|
  | `AREA_REAPED` | Ministry definition |
  | `AREA_HARVESTED` | FAO definition, kept apart: they are not assumed equal |
  | `PRODUCTION` | |
  | `YIELD` | |
  | `FARMGATE_PRICE` | J$/kg, nominal |
  | `PRODUCER_PRICE_LCU` | |
  | `PRODUCER_PRICE_USD` | |

  The definitions to confirm against each publication's notes are written in the file.

## 6. Provenance and revisions

```
source -> dataset -> publication (file, SHA-256, retrieved at/by, supersedes) -> ingestion run (parser, version, mode, counts)
       -> raw observation (every row as read) -> validation issues
       -> observation (value, unit, canonical value, status, revision, supersedes, is_current)
```

- **One current figure:** exactly one current figure per dataset, measure, crop, area and period (a partial unique
  index enforces it).
- **Revisions:** a later publication with a different value creates revision n+1, linked to the one it supersedes.
  `FINAL` becomes `REVISED`.
- **FAO flags:** stored in `source_flag`. E (estimated), I (imputed) and M (missing) become `ESTIMATE`.

## 7. Validation rules

| Rule | Severity | Effect |
|---|---|---|
| `REQUIRED_FIELD` | ERROR | row rejected |
| `UNKNOWN_CROP`, `UNKNOWN_AREA`, `UNKNOWN_MEASURE`, `UNKNOWN_UNIT` | ERROR | row rejected; add a reviewed mapping |
| `UNIT_MEASURE_MISMATCH` (for example hectares for production) | ERROR | row rejected |
| `INVALID_PERIOD`, `INVALID_NUMBER`, `NEGATIVE_VALUE`, `INVALID_STATUS` | ERROR | row rejected |
| `CONFLICTING_DUPLICATE` (same figure twice in one file with different values) | ERROR | second row rejected |
| `UNIT_MISMATCH` (FAOSTAT unit differs from the verified map) | ERROR | row kept as FAOSTAT only |
| `OUTLIER_PERIOD_CHANGE` (more than 5× change from the previous period) | WARNING | accepted; check the source |
| `REVISION` | INFO | new revision recorded |
| `UNVERIFIED_ELEMENT`, `UNVERIFIED_ITEM`, `NO_VALUE` | INFO | kept as a FAOSTAT row only |

**Limits:** files of 20 MB and 200,000 rows at most; UTF-8 only.

**Planned later:** a yield consistency check (production ÷ area against yield, within 10%) and parish-sum
reconciliation against all-island totals.

## 8. Rights review: product-owner decisions (5 November 2026) and records

### Ministry of Agriculture (AMID)

- **Decision:** the product owner will seek written permission to store, process, analyse and model the statistics,
  including the intended commercial uses.
- **Status:** `PERMISSION_REQUIRED`. The licence gate stays; no real Ministry dataset may be applied.
- **Draft request** (uses, attribution, derived analytics, optional AI processing, request for machine-readable
  data): `MOA_DATA_PERMISSION_REQUEST.md`.

### FAOSTAT

**Status:** `NOT_REVIEWED`, awaiting rights review. It is never marked approved automatically.

**Record of the official terms** (FAO Statistical Database Terms of Use, https://www.fao.org/contact-us/terms/db-terms-of-use/en/, read 5 November 2026):

| Item | What the terms say |
|---|---|
| Licence | Datasets are licensed under CC BY 4.0, "unless specified otherwise in their metadata or webpage", supplemented by additional terms |
| Prohibited uses | No attempt to de-anonymise; **no use to promote a company or its products**; no use that falsifies or misrepresents the content |
| Third-party data | The user must determine whether a dataset is fully or partly owned by third parties and comply with their terms; FAO does not guarantee it owns all rights |
| Endorsement | The user may not represent that FAO participated in, sponsored, approved or endorsed the use |
| Liability | Provided without warranty; FAO may modify or discontinue databases; no liability for loss or damage |
| Disputes | UNCITRAL arbitration |
| Amendments | FAO's terms for reuse of web content are incorporated; both may change, and continued use means acceptance |
| Required citation | "FAO. [year of last update]. [Name of database: dataset]. [Accessed on DD Month YYYY]. [URL]. Licence: CC-BY-4.0." |

**Uses that need clarification before approval:**
1. Whether showing FAOSTAT figures inside a commercial service, or in KoroFarm's own product materials, counts as
   "promoting a company or its products".
2. The metadata of the QCL and PP datasets for Jamaica: confirm no dataset-specific licence or third-party ownership
   applies.
3. Whether derived analytics and forecasts built partly on FAOSTAT may be shown commercially, and how they must be
   labelled (KoroFarm estimates, never FAO figures; no implied endorsement).
4. Whether sending FAOSTAT figures, or forecasts derived from them, to an external AI provider is consistent with
   the terms. Even if it is, it needs KoroFarm's own explicit per-model-run decision (§10).

### Attribution

Every page or answer that shows a figure shows its source's attribution text, which is stored per source.

### Derived data

A forecast's rights are a separate, explicit decision per model run and purpose (`agri.derived_rights_decisions`,
migration 0030). It is never inferred from the source licences. See `ML_AND_LLM.md`.

## 8a. Licensing review (product owner actions)

1. **Ministry of Agriculture.** Write to request permission to store and analyse AMID statistics, and to show
   derived figures with attribution. Record the answer, then set `licence_review_status` to `APPROVED` (or
   `REJECTED`) with the conditions.
2. **FAOSTAT.** Confirm the CC BY 4.0 terms and the attribution text, then set `APPROVED`.
3. **Attribution.** Every page or answer that shows a figure shows its source's attribution text (stored per source).

## 9. Future API contracts

Not implemented, and not needed for the first imports.

- **FAOSTAT.** FAO offers bulk downloads and an API; the exact API endpoints and any key requirement are to be
  confirmed when connectivity is authorized.

  The adapter contract is fixed regardless:
  - an adapter only **retrieves a file** and registers it as a publication (SHA-256);
  - parsing always goes through `import_faostat`, so an API pull and a manual download behave identically;
  - it runs on a schedule only after authorization, with backoff and a polite rate limit.
- **Ministry.** No API exists. An adapter would watch the dataset pages for new PDF editions and register them.
  Extraction would run in dry-run mode, with a human comparing each table before `--apply`.
- **Internal read API** (for dashboards and the evidence layer). Read-only endpoints over `agri`:
  - `GET /agri/series?crop=&measure=&area=&from=&to=`;
  - `GET /agri/publications?source=`;
  - `GET /agri/forecasts?crop=&measure=&area=`.

  Each returns provenance and attribution with every figure. They will use `QUERY_CATALOGUE` in
  `app/agriculture/evidence.py`, through the read-only role (`deploy/sql/agri_readonly_role.sql`).

## 10. Code and tests

| Piece | File |
|---|---|
| Schema | `src/backend/alembic/versions/0029_agricultural_intelligence.py` (reviewed SQL: `deploy/sql/wp5_0028_0029_upgrade.sql`) |
| Mapping | `src/backend/app/agriculture/domain/models.py` |
| Importer | `src/backend/app/agriculture/ingestion.py`; command `src/backend/scripts/agri_import.py` |
| Tests (PostgreSQL) | `src/backend/tests/test_agriculture_postgres.py`:<br>• the schema matches the mapping and stays closed;<br>• constraints and the one-current-revision rule hold;<br>• a downgrade refuses to drop data;<br>• dry run, licence gate, idempotency, revisions and outliers;<br>• FAOSTAT verified-only mapping;<br>• read-only evidence queries;<br>• stored model runs;<br>• the read-only role |
