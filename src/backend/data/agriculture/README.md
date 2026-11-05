# Agricultural reference data and import templates

Reviewed inputs for the `agri` schema (migration 0029). **No statistics are stored here**: only definitions,
mappings and empty templates. Load them with
`python -m src.backend.scripts.agri_import reference` (dry run), then `--apply`.

| Folder | Contents |
|---|---|
| `reference/` | `sources.csv` and `datasets.csv` (catalogue with licence review status); `units.csv` and `measures.csv` (definitions and conversions); `crops.csv` and `crop_aliases.csv`; `geo_areas.csv` and `geo_aliases.csv` (Jamaica and its 14 parishes); `faostat_element_map.csv` |
| `templates/` | Empty CSV templates: observations, publication register, crop and geography aliases |

**Rules:**
- Every change here is a reviewed pull request.
- Loading is additive: an existing row is never changed or deleted by the loader.
- FAO item codes and the FAOSTAT element map are marked unverified (`false`) until checked against a real download.
  Until then FAOSTAT rows are kept only with FAO's own codes.
- The Ministry of Agriculture's data is marked `PERMISSION_REQUIRED` and FAOSTAT `NOT_REVIEWED`. The importer refuses
  `--apply` for both until the product owner records a licence decision.

Full specification: `docs/integrations/AGRICULTURAL_DATA.md`.
