# Agricultural data sources

Acquired and inspected October 17, 2026. All 37 linked Ministry PDFs downloaded successfully; no manual Ministry downloads are needed. Four discovery index HTML snapshots are retained in `data/agriculture/raw/`. No 2026 observations were linked on those indexes.

## Coverage and validation

| Measurement | Retrieved quarterly cells after reconciliation | Validated | Gap |
|---|---:|---:|---|
| Iceberg production (tonnes) | 40 | 39 | 2016 Q3 quarantined |
| Area reaped (hectares) | 40 | 40 | None |
| Farmgate price (JMD/kg) | 40 | 40 | None |

Coverage: 2016 Q1–2025 Q4. Files include 10 production, 10 area, 9 price and 8 combined annual PDFs. The price index omits 2020; the combined 2020 document supplies its four verified price cells. The combined index omits 2017–2018; dedicated annual production/area/price documents supply those years. There are 212 extracted quarterly cells across overlapping sources and 120 normalized natural keys; source overlaps are evidence, not extra observations.

Mapping is limited to the Ministry spellings ICEBURG LETTUCE, ICEBURGH LETTUCE and ICEBERG LETTUCE. Reviewed overlapping tables use the same dedicated iceberg row and matching period/unit cells except the explicit conflict below. OTHER LETTUCE and international lettuce/chicory aggregates are never merged.

## Quarantine and reconciliation

2016 Q3 production is 2,525 tonnes in the dedicated production PDF (page 1) and 2,998 in the combined PDF (page 3). Both original cells were visually checked; the conflict is present in the sources, not a text-extraction error. Both values remain in provenance; the normalized value is null and excluded from modelling. Area and prices remain usable. Request Ministry clarification before resolving this cell.

All 61 iceberg source rows across the 37 PDFs were rendered and visually inspected against their extracted values. Review strips are in `tmp/agriculture/source-row-review-{1,2,3}.png`; the original PDFs, text rows and page numbers remain the durable evidence. No OCR was used.

The six 2025 production/price sanity checks pass against the original PDFs. Annual production and area checks compare the four displayed quarterly cells with the displayed annual cell. Differences up to 2.5 displayed units are flagged as compatible with independent rounding of five cells, not silently corrected. Annual prices are not summed or assumed to be simple averages.

Annual reconciliation results:
- 2025 production: quarter sum 16533, annual 16532, difference 1; within_rounding_tolerance.
- 2024 production: quarter sum 14614, annual 14615, difference -1; within_rounding_tolerance.
- 2023 production: quarter sum 15076, annual 15076, difference 0; exact.
- 2022 production: quarter sum 16592, annual 16592, difference 0; exact.
- 2021 production: quarter sum 14735, annual 14736, difference -1; within_rounding_tolerance.
- 2020 production: quarter sum 12680, annual 12680, difference 0; exact.
- 2019 production: quarter sum 12119, annual 12119, difference 0; exact.
- 2018 production: quarter sum 13051, annual 13051, difference 0; exact.
- 2017 production: quarter sum 10791, annual 10791, difference 0; exact.
- 2016 production: quarter sum 11641, annual 11641, difference 0; exact.
- 2025 area: quarter sum 1196, annual 1196, difference 0; exact.
- 2024 area: quarter sum 1088, annual 1088, difference 0; exact.
- 2023 area: quarter sum 1111, annual 1110, difference 1; within_rounding_tolerance.
- 2022 area: quarter sum 1174, annual 1173, difference 1; within_rounding_tolerance.
- 2021 area: quarter sum 1029, annual 1029, difference 0; exact.
- 2020 area: quarter sum 902, annual 902, difference 0; exact.
- 2019 area: quarter sum 875, annual 875, difference 0; exact.
- 2018 area: quarter sum 911, annual 911, difference 0; exact.
- 2017 area: quarter sum 759, annual 759, difference 0; exact.
- 2016 area: quarter sum 796, annual 796, difference 0; exact.

Publication dates/revision vintages are unknown. Retrieval timestamps and HTTP Last-Modified headers are preserved, but neither is used as proof that a value was known at a historical forecast origin. Source estimates are not described as finalized ground truth. Asterisks are preserved as source annotations with unknown meaning.

## Official source inventory

Each link below is the original PDF; full checksums, retrieval times, headers and parent index URLs are in `data/agriculture/sources.json`.

| Year | Dataset | Original PDF | Local original |
|---|---|---|---|
| 2016 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/Area_reaped_2016.pdf) | `data/agriculture/raw/area-2016-e12d7d769ed8.pdf` |
| 2016 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate%202016.pdf) | `data/agriculture/raw/combined-2016-05dbbdcda186.pdf` |
| 2016 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2016.pdf) | `data/agriculture/raw/price-2016-901fde412610.pdf` |
| 2016 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2016_0.pdf) | `data/agriculture/raw/production-2016-072ab27638b2.pdf` |
| 2017 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2017.pdf) | `data/agriculture/raw/area-2017-ca072da3c8dd.pdf` |
| 2017 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2017.pdf) | `data/agriculture/raw/price-2017-8f112005957a.pdf` |
| 2017 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2017.pdf) | `data/agriculture/raw/production-2017-bd3312629ca8.pdf` |
| 2018 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2018.pdf) | `data/agriculture/raw/area-2018-947e6462964f.pdf` |
| 2018 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2018.pdf) | `data/agriculture/raw/price-2018-ce74f4e5ece7.pdf` |
| 2018 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2018.pdf) | `data/agriculture/raw/production-2018-74c4f4573bc8.pdf` |
| 2019 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2019.pdf) | `data/agriculture/raw/area-2019-785ef3b3a4ab.pdf` |
| 2019 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate%202019_0.pdf) | `data/agriculture/raw/combined-2019-003850dedbe0.pdf` |
| 2019 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2019_0.pdf) | `data/agriculture/raw/price-2019-9495f11ac443.pdf` |
| 2019 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2019_0.pdf) | `data/agriculture/raw/production-2019-6f53fe48071f.pdf` |
| 2020 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2020.pdf) | `data/agriculture/raw/area-2020-fec0a9e52175.pdf` |
| 2020 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate%202020.pdf) | `data/agriculture/raw/combined-2020-6adea4781f87.pdf` |
| 2020 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2020_1.pdf) | `data/agriculture/raw/production-2020-d897aabe1b54.pdf` |
| 2021 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2021.pdf) | `data/agriculture/raw/area-2021-a35dc1dea3e3.pdf` |
| 2021 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate%202021.pdf) | `data/agriculture/raw/combined-2021-23ba294b3b17.pdf` |
| 2021 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2021.pdf) | `data/agriculture/raw/price-2021-adc1db58a3ec.pdf` |
| 2021 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2021.pdf) | `data/agriculture/raw/production-2021-11bce5ac96aa.pdf` |
| 2022 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2022.pdf) | `data/agriculture/raw/area-2022-81094b2bdd2f.pdf` |
| 2022 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate%202022.pdf) | `data/agriculture/raw/combined-2022-f155ff007616.pdf` |
| 2022 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2022.pdf) | `data/agriculture/raw/price-2022-60fdb7d08b17.pdf` |
| 2022 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2022.pdf) | `data/agriculture/raw/production-2022-315510e880e7.pdf` |
| 2023 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2023.pdf) | `data/agriculture/raw/area-2023-f467dc7cf9b7.pdf` |
| 2023 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_2023.pdf) | `data/agriculture/raw/combined-2023-bd61edbd2089.pdf` |
| 2023 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2023.pdf) | `data/agriculture/raw/price-2023-230f03ac39e6.pdf` |
| 2023 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2023.pdf) | `data/agriculture/raw/production-2023-6ec85ea01682.pdf` |
| 2024 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2024.pdf) | `data/agriculture/raw/area-2024-d5f37fd602c4.pdf` |
| 2024 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_2024.pdf) | `data/agriculture/raw/combined-2024-778d4b401297.pdf` |
| 2024 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2024.pdf) | `data/agriculture/raw/price-2024-ffcf22b7ab37.pdf` |
| 2024 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2024.pdf) | `data/agriculture/raw/production-2024-5e4888811d4c.pdf` |
| 2025 | area | [Ministry PDF](https://moa.gov.jm/sites/default/files/area_reaped_by_quarter_2025.pdf) | `data/agriculture/raw/area-2025-59fe4bdb3c31.pdf` |
| 2025 | combined | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_2025.pdf) | `data/agriculture/raw/combined-2025-50ef4f092036.pdf` |
| 2025 | price | [Ministry PDF](https://moa.gov.jm/sites/default/files/farmgate_prices_2025.pdf) | `data/agriculture/raw/price-2025-cd2b98ce2920.pdf` |
| 2025 | production | [Ministry PDF](https://moa.gov.jm/sites/default/files/crop_production_by_quarter_2025.pdf) | `data/agriculture/raw/production-2025-446def511719.pdf` |

## FAOSTAT API acquisition (Checkpoint 1 update)

The earlier HTTP 403 limitation was transient and is resolved. The official Developer Portal was inspected at https://www.fao.org/faostat/en/#developer-portal . Its view/template links to https://www.fao.org/faostat/en/docs/faostat_openapi.yaml . The current production server documented there is https://faostatservices.fao.org/api/v1 . The official browser client at https://www.fao.org/faostat/en/src/js/FAOSTATAPIClient.js documents the anonymous guest handshake used during this acquisition.

Successful access method: GET `/auth/guest`, retain the returned bearer token in memory, then authenticated GET requests to the documented `/en/codes/area/QCL/`, `/en/codes/element/QCL/`, `/en/bulkdownloads/QCL/` and `/en/data/QCL` endpoints. Tokens are never written into receipts, raw dataset files or frontend bundles. A personal `FAOSTAT_ACCESS_TOKEN` can be supplied for ongoing server ingestion; the portal also documents personal sign-in and `/auth/login`. No user credentials were required for this successful guest acquisition. If guest access later returns 401/403, the CLI identifies that status and requests a valid personal token rather than inventing another endpoint.

Jamaica code 109 was verified from the official area metadata. Element query codes were resolved from official element labels: 2312 for Area harvested and 2510 for Production Quantity. The response uses legacy output codes 5312, 5510 and 5513, which are retained verbatim. The adapter explicitly validates returned labels/units; it does not assume query and output codes are identical.

The query requested Jamaica QCL production and harvested area for 2016 through 2025. The genuine response contains **1,496 annual observations for 2016-2024 across 105 source item categories**, including aggregates and livestock products. It returned no 2025 rows. There are **558 harvested-area observations in hectares**, **929 production observations in tonnes**, and **9 production observations in thousands of units**. The latter keep their original unit; they are never treated as tonnes. These categories must not be summed into total agricultural production because aggregate and component items coexist.

Source classifications remain explicit: 949 A (official value), 195 E (estimated), 338 I (imputed by a receiving agency), and 14 X (external organization). Validation means schema, units, scope and provenance checks passed, not that estimated/imputed values became independently verified measurements. No additional values were manufactured by KoroFarm.

`Lettuce and chicory` (source FAO item code 372) has 18 annual production/area records for 2016-2024. This broader category has no Ministry crop mapping, remains annual with quarter=null, and is excluded from the iceberg forecasting feature/target series. The UI exposes it as separate annual context. Other items and series gaps are preserved in the annual artifact rather than silently made complete.

Local evidence:

- `data/agriculture/faostat/qcl-jamaica-2016-2025-source.json`: exact query URL, requested years, retrieval metadata, access method, source and official contract checksums/local files.
- `data/agriculture/faostat/raw/`: immutable original API response, area/element/bulk metadata and Developer Portal/OpenAPI source snapshots.
- `data/agriculture/faostat/qcl-jamaica-2016-2025.json`: 1,496 annual normalized records, full validation counts, flags, requested-year gaps and per-item/measurement/unit gaps.
- Authenticated `GET /agricultural-intelligence/faostat?item_code=372`: separate annual sample/context; unsupported items return 404 and unavailable artifacts 503.

```powershell
.venv\Scripts\python.exe -m src.backend.scripts.acquire_faostat
# Explicit network refresh; preserves original response versions:
.venv\Scripts\python.exe -m src.backend.scripts.acquire_faostat --refresh
```

Repeated default acquisition revalidates the cached checksum and imports idempotently without network access. Original normalized CSV import remains supported through `src.backend.scripts.import_faostat`; only official HTTPS FAO source URLs are accepted. No manually downloaded FAOSTAT file is currently required.
