"""Offline, idempotent import of agricultural statistics into the `agri` schema (R1 WP5 preparation).

No network access: every input is a local file someone retrieved and registered. Nothing is fetched from the
Ministry of Agriculture or FAOSTAT here (docs/integrations/AGRICULTURAL_DATA.md).

Guarantees
* Dry run by default. A dry run does all the work inside a savepoint and rolls it back, returning the report.
* Licence gate: `apply` is refused unless the source's licence review is APPROVED (the Ministry's data currently says
  "All Rights Reserved"; FAOSTAT's CC BY 4.0 still needs the product owner's confirmation).
* Idempotent: a file is identified by its SHA-256. Applying the same file again changes nothing and says so.
* Provenance: every source row is kept as read (raw_observations), linked to its publication and ingestion run.
* Validation: each rejected row has recorded issues (validation_issues); accepted rows are unit-normalised.
* Revisions: a different value for the same dataset, measure, crop, area and period becomes a new revision; the old
  one stays, marked not current. Values are never overwritten or deleted.
* Unverified mappings never become statistics: FAOSTAT rows are always kept with FAO's own codes, but they become
  observations only through a verified element mapping and a crop whose FAO item code is verified.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.agriculture.domain.models import (
    Crop, CropAlias, Dataset, FaostatObservation, GeoAlias, GeoArea, IngestionRun, Measure, Observation, Publication,
    RawObservation, Source, Unit, ValidationIssue,
)

PARSER_VERSION = "1"
REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "agriculture" / "reference"
MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 200_000
STATUSES = {"PROVISIONAL", "REVISED", "FINAL", "ESTIMATE"}
OUTLIER_RATIO = Decimal("5")
TEMPLATE_COLUMNS = ["source_code", "dataset_code", "crop", "geography", "measure", "period_type", "period", "value", "unit",
                    "status", "quality_flag", "source_row_reference", "notes"]
FAOSTAT_COLUMNS = {"Area Code", "Area", "Item Code", "Item", "Element Code", "Element", "Year", "Unit", "Value"}


class ImportRefused(ValueError):
    """The import cannot run at all (licence, unknown dataset, unreadable file). Nothing was written."""


@dataclass
class ImportReport:
    mode: str
    status: str = "SUCCEEDED"
    dataset: str = ""
    content_sha256: str = ""
    publication_id: str | None = None
    ingestion_run_id: str | None = None
    rows_read: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_duplicate: int = 0
    revisions: int = 0
    faostat_rows: int = 0
    issues: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def normalize(text: str) -> str:
    """Matching key for names: case, punctuation, '&' and 'Saint/St.' differences do not matter."""
    value = text.upper().replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9 ]+", " ", value)
    value = re.sub(r"\bSAINT\b", "ST", value)
    return re.sub(r"\s+", " ", value).strip()


def file_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_period(period_type: str, period: str) -> tuple[date, date]:
    """YEAR '2024'; QUARTER '2024-Q1'; MONTH '2024-03'."""
    period = period.strip()
    if period_type == "YEAR" and re.fullmatch(r"\d{4}", period):
        year = int(period)
        return date(year, 1, 1), date(year, 12, 31)
    if period_type == "QUARTER" and (match := re.fullmatch(r"(\d{4})-Q([1-4])", period.upper())):
        year, quarter = int(match.group(1)), int(match.group(2))
        start = date(year, 3 * quarter - 2, 1)
        end = date(year, 12, 31) if quarter == 4 else date.fromordinal(date(year, 3 * quarter + 1, 1).toordinal() - 1)
        return start, end
    if period_type == "MONTH" and (match := re.fullmatch(r"(\d{4})-(\d{2})", period)):
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            following = date(year + (month == 12), month % 12 + 1, 1)
            return date(year, month, 1), date.fromordinal(following.toordinal() - 1)
    raise ValueError(f"period {period!r} does not match period type {period_type!r}")


def _read_csv(path: Path) -> tuple[bytes, list[dict]]:
    content = path.read_bytes()
    if len(content) > MAX_BYTES:
        raise ImportRefused(f"{path.name} is larger than {MAX_BYTES // (1024 * 1024)} MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportRefused(f"{path.name} is not UTF-8 text") from exc
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) > MAX_ROWS:
        raise ImportRefused(f"{path.name} has more than {MAX_ROWS} rows")
    return content, rows


# --- Reference data ---------------------------------------------------------------------------------------------

def load_reference(session: Session, directory: Path = REFERENCE_DIR, apply: bool = False) -> dict:
    """Insert reference rows (sources, datasets, units, measures, crops, areas, aliases) that do not exist yet.
    Existing rows are never changed or deleted: corrections are reviewed and applied deliberately."""
    counts: dict[str, int] = {}
    savepoint = session.begin_nested()

    def rows(name: str) -> list[dict]:
        return _read_csv(directory / name)[1]

    def add(kind: str, exists, make) -> None:
        if exists is None:
            session.add(make())
            session.flush()
            counts[kind] = counts.get(kind, 0) + 1

    for row in rows("sources.csv"):
        add("sources", session.scalar(select(Source).where(Source.code == row["code"])), lambda row=row: Source(
            code=row["code"], name=row["name"], publisher=row["publisher"], homepage_url=row["homepage_url"] or None,
            licence_name=row["licence_name"] or None, licence_url=row["licence_url"] or None,
            licence_review_status=row["licence_review_status"], reuse_conditions=row["reuse_conditions"] or None,
            attribution_text=row["attribution_text"] or None, contact=row["contact"] or None))
    sources = {s.code: s.id for s in session.scalars(select(Source))}
    for row in rows("datasets.csv"):
        add("datasets", session.scalar(select(Dataset).where(Dataset.source_id == sources[row["source_code"]], Dataset.code == row["code"])),
            lambda row=row: Dataset(source_id=sources[row["source_code"]], code=row["code"], title=row["title"],
                                    landing_url=row["landing_url"] or None, format=row["format"], frequency=row["frequency"],
                                    geographic_level=row["geographic_level"], measures=row["measures"].split("|"), notes=row["notes"] or None))
    for row in rows("units.csv"):
        add("units", session.get(Unit, row["code"]), lambda row=row: Unit(
            code=row["code"], dimension=row["dimension"], canonical_code=row["canonical_code"],
            factor_to_canonical=Decimal(row["factor_to_canonical"]), description=row["description"]))
    for row in rows("measures.csv"):
        add("measures", session.get(Measure, row["code"]), lambda row=row: Measure(
            code=row["code"], name=row["name"], canonical_unit_code=row["canonical_unit_code"], definition=row["definition"],
            non_negative=row["non_negative"].lower() == "true"))
    for row in rows("crops.csv"):
        add("crops", session.scalar(select(Crop).where(Crop.code == row["code"])), lambda row=row: Crop(
            code=row["code"], name=row["name"], scientific_name=row["scientific_name"] or None, category=row["category"] or None,
            operational_crop_code=row["operational_crop_code"] or None,
            fao_item_code=int(row["fao_item_code"]) if row["fao_item_code"] else None,
            fao_item_code_verified=row["fao_item_code_verified"].lower() == "true"))
    for row in rows("geo_areas.csv"):
        parent = session.scalar(select(GeoArea.id).where(GeoArea.code == row["parent_code"])) if row["parent_code"] else None
        add("geo_areas", session.scalar(select(GeoArea).where(GeoArea.code == row["code"])), lambda row=row, parent=parent: GeoArea(
            code=row["code"], name=row["name"], level=row["level"], parent_id=parent, iso_3166_code=row["iso_3166_code"] or None,
            m49_code=row["m49_code"] or None, fao_area_code=int(row["fao_area_code"]) if row["fao_area_code"] else None))
    crops = {c.code: c.id for c in session.scalars(select(Crop))}
    areas = {g.code: g.id for g in session.scalars(select(GeoArea))}
    # Every crop and area name is its own alias, so canonical names always resolve.
    alias_rows = [("crop_aliases", CropAlias, "crop_id", crops[c.code], c.name, None) for c in session.scalars(select(Crop))]
    alias_rows += [("geo_aliases", GeoAlias, "geo_area_id", areas[g.code], g.name, None) for g in session.scalars(select(GeoArea))]
    alias_rows += [("crop_aliases", CropAlias, "crop_id", crops[r["crop_code"]], r["alias"], sources.get(r["source_code"]))
                   for r in rows("crop_aliases.csv")]
    alias_rows += [("geo_aliases", GeoAlias, "geo_area_id", areas[r["geo_code"]], r["alias"], sources.get(r["source_code"]))
                   for r in rows("geo_aliases.csv")]
    for kind, model, column, target, alias, source_id in alias_rows:
        key = normalize(alias)
        existing = session.scalar(select(model).where(model.alias_normalized == key, model.source_id.is_(None) if source_id is None
                                                      else model.source_id == source_id))
        add(kind, existing, lambda model=model, column=column, target=target, alias=alias, key=key, source_id=source_id:
            model(**{column: target}, alias=alias, alias_normalized=key, source_id=source_id))
    if not apply:
        savepoint.rollback()
    else:
        savepoint.commit()
    return counts


# --- Shared pieces of an import run ---------------------------------------------------------------------------------

def _dataset(session: Session, source_code: str, dataset_code: str) -> tuple[Source, Dataset]:
    source = session.scalar(select(Source).where(Source.code == source_code))
    if source is None:
        raise ImportRefused(f"unknown source {source_code!r}; load the reference data first")
    dataset = session.scalar(select(Dataset).where(Dataset.source_id == source.id, Dataset.code == dataset_code))
    if dataset is None:
        raise ImportRefused(f"unknown dataset {source_code}/{dataset_code}")
    return source, dataset


def _start(session: Session, source: Source, dataset: Dataset, content: bytes, *, path: Path, parser: str, apply: bool,
           operator: str, version_label: str, retrieval_url: str | None, report: ImportReport) -> tuple[Publication, IngestionRun] | None:
    if apply and source.licence_review_status != "APPROVED":
        raise ImportRefused(f"source {source.code} licence review is {source.licence_review_status}; only a dry run is allowed "
                            "until the product owner records the licence as APPROVED")
    digest = file_digest(content)
    report.content_sha256, report.dataset = digest, f"{source.code}/{dataset.code}"
    key = f"{source.code}:{dataset.code}:{digest}:{parser}:{PARSER_VERSION}"
    done = session.scalar(select(IngestionRun).where(IngestionRun.idempotency_key == key, IngestionRun.status == "SUCCEEDED"))
    if done is not None:
        report.status, report.ingestion_run_id, report.publication_id = "ALREADY_IMPORTED", str(done.id), str(done.publication_id)
        return None
    publication = session.scalar(select(Publication).where(Publication.dataset_id == dataset.id, Publication.content_sha256 == digest))
    if publication is None:
        previous = session.scalar(select(Publication).where(Publication.dataset_id == dataset.id, Publication.status != "SUPERSEDED")
                                  .order_by(Publication.retrieved_at.desc()).limit(1))
        publication = Publication(dataset_id=dataset.id, version_label=version_label, retrieved_at=datetime.now(timezone.utc),
                                  retrieval_url=retrieval_url, file_name=path.name, content_sha256=digest, byte_size=len(content),
                                  retrieved_by=operator, supersedes_publication_id=previous.id if previous else None)
        session.add(publication)
        session.flush()
    run = IngestionRun(dataset_id=dataset.id, publication_id=publication.id, idempotency_key=key if apply else f"{key}:dry-run:{uuid4()}",
                       parser_code=parser, parser_version=PARSER_VERSION, mode="APPLY" if apply else "DRY_RUN", status="RUNNING",
                       operator=operator)
    session.add(run)
    session.flush()
    report.publication_id, report.ingestion_run_id = str(publication.id), str(run.id)
    return publication, run


def _raw(session: Session, run: IngestionRun, publication: Publication, number: int, row: dict) -> RawObservation | None:
    payload = {k: (v if v is None else str(v)) for k, v in row.items() if k is not None}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if session.scalar(select(RawObservation.id).where(RawObservation.publication_id == publication.id, RawObservation.row_sha256 == digest)):
        return None
    raw = RawObservation(ingestion_run_id=run.id, publication_id=publication.id, row_number=number, raw=payload, row_sha256=digest)
    session.add(raw)
    session.flush()
    return raw


def _issue(session: Session, report: ImportReport, run: IngestionRun, raw: RawObservation | None, number: int, rule: str,
           severity: str, message: str, column: str | None = None) -> None:
    session.add(ValidationIssue(ingestion_run_id=run.id, raw_observation_id=raw.id if raw else None, row_number=number,
                                rule_code=rule, severity=severity, field=column, message=message[:1000]))
    report.issues.append({"row": number, "rule": rule, "severity": severity, "field": column, "message": message})


def _resolve(session: Session, model, column: str, name: str, source_id: UUID) -> UUID | None:
    key = normalize(name)
    for scope in (model.source_id == source_id, model.source_id.is_(None)):
        found = session.scalar(select(getattr(model, column)).where(model.alias_normalized == key, scope))
        if found is not None:
            return found
    return None


def _record(session: Session, report: ImportReport, run: IngestionRun, publication: Publication, dataset: Dataset,
            raw: RawObservation | None, number: int, *, measure: Measure, unit: Unit, crop_id: UUID, area_id: UUID,
            period_type: str, start: date, end: date, value: Decimal, status: str, quality_flag: str | None,
            source_flag: str | None) -> None:
    canonical = value * unit.factor_to_canonical
    current = session.scalar(select(Observation).where(
        Observation.dataset_id == dataset.id, Observation.measure_code == measure.code, Observation.crop_id == crop_id,
        Observation.geo_area_id == area_id, Observation.period_type == period_type, Observation.period_start == start,
        Observation.is_current.is_(True)).with_for_update())
    if current is not None and current.value_canonical == canonical and current.status == status:
        report.rows_duplicate += 1
        return
    previous = session.scalar(select(Observation.value_canonical).where(
        Observation.dataset_id == dataset.id, Observation.measure_code == measure.code, Observation.crop_id == crop_id,
        Observation.geo_area_id == area_id, Observation.period_type == period_type, Observation.period_start < start,
        Observation.is_current.is_(True)).order_by(Observation.period_start.desc()).limit(1))
    if previous and previous > 0 and canonical > 0 and (canonical / previous > OUTLIER_RATIO or previous / canonical > OUTLIER_RATIO):
        _issue(session, report, run, raw, number, "OUTLIER_PERIOD_CHANGE", "WARNING",
               f"{measure.code} changed more than {OUTLIER_RATIO}x from the previous period; accepted, check the source", "value")
    revision = 1
    if current is not None:
        current.is_current = False
        session.flush()
        revision = current.revision_number + 1
        report.revisions += 1
        _issue(session, report, run, raw, number, "REVISION", "INFO",
               f"replaces revision {current.revision_number} ({current.value} {current.unit_code}) from publication {current.publication_id}")
    session.add(Observation(
        dataset_id=dataset.id, publication_id=publication.id, raw_observation_id=raw.id if raw else None, measure_code=measure.code,
        crop_id=crop_id, geo_area_id=area_id, period_type=period_type, period_start=start, period_end=end, value=value,
        unit_code=unit.code, value_canonical=canonical, canonical_unit_code=measure.canonical_unit_code,
        status="REVISED" if current is not None and status == "FINAL" else status, quality_flag=quality_flag,
        source_flag=source_flag, revision_number=revision, supersedes_id=current.id if current else None, is_current=True))
    session.flush()
    report.rows_accepted += 1


def _finish(session: Session, savepoint, run: IngestionRun, publication: Publication, report: ImportReport, apply: bool) -> ImportReport:
    run.rows_read, run.rows_accepted = report.rows_read, report.rows_accepted
    run.rows_rejected, run.rows_duplicate = report.rows_rejected, report.rows_duplicate
    run.status, run.finished_at = "SUCCEEDED", datetime.now(timezone.utc)
    publication.status = "PARSED"
    session.flush()
    if apply:
        savepoint.commit()
    else:
        savepoint.rollback()
        report.publication_id = report.ingestion_run_id = None  # nothing was kept
    return report


# --- KoroFarm template (Ministry tables transcribed into data/agriculture/templates/observations_template.csv) -------

def import_observations(session: Session, path: Path, *, operator: str, apply: bool = False, version_label: str | None = None,
                        retrieval_url: str | None = None) -> ImportReport:
    content, rows = _read_csv(path)
    report = ImportReport(mode="APPLY" if apply else "DRY_RUN")
    if not rows:
        raise ImportRefused(f"{path.name} has no data rows")
    missing = set(TEMPLATE_COLUMNS) - set(rows[0])
    if missing:
        raise ImportRefused(f"{path.name} is missing template columns: {sorted(missing)}")
    pairs = {(r["source_code"].strip(), r["dataset_code"].strip()) for r in rows}
    if len(pairs) != 1:
        raise ImportRefused("one file must hold one dataset (found " + ", ".join(sorted("/".join(p) for p in pairs)) + ")")
    source_code, dataset_code = pairs.pop()
    source, dataset = _dataset(session, source_code, dataset_code)
    savepoint = session.begin_nested()
    try:
        started = _start(session, source, dataset, content, path=path, parser="korofarm_template", apply=apply, operator=operator,
                         version_label=version_label or path.name, retrieval_url=retrieval_url, report=report)
    except ImportRefused:
        savepoint.rollback()
        raise
    if started is None:
        savepoint.rollback()
        return report
    publication, run = started
    measures = {m.code: m for m in session.scalars(select(Measure))}
    units = {u.code: u for u in session.scalars(select(Unit))}
    seen: dict[tuple, Decimal] = {}
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        report.rows_read += 1
        raw = _raw(session, run, publication, number, row)
        if raw is None:
            report.rows_duplicate += 1
            continue
        errors_before = sum(1 for i in report.issues if i["severity"] == "ERROR")

        def error(rule: str, message: str, column: str | None = None) -> None:
            _issue(session, report, run, raw, number, rule, "ERROR", message, column)

        for column in ("crop", "geography", "measure", "period_type", "period", "value", "unit", "status"):
            if not (row.get(column) or "").strip():
                error("REQUIRED_FIELD", f"{column} is empty", column)
        if sum(1 for i in report.issues if i["severity"] == "ERROR") > errors_before:
            report.rows_rejected += 1
            continue
        crop_id = _resolve(session, CropAlias, "crop_id", row["crop"], source.id)
        area_id = _resolve(session, GeoAlias, "geo_area_id", row["geography"], source.id)
        measure, unit = measures.get(row["measure"].strip().upper()), units.get(row["unit"].strip().upper())
        status, period_type = row["status"].strip().upper(), row["period_type"].strip().upper()
        if crop_id is None:
            error("UNKNOWN_CROP", f"crop {row['crop']!r} has no mapping; add a reviewed alias", "crop")
        if area_id is None:
            error("UNKNOWN_AREA", f"geography {row['geography']!r} has no mapping; add a reviewed alias", "geography")
        if measure is None:
            error("UNKNOWN_MEASURE", f"measure {row['measure']!r} is not defined", "measure")
        if unit is None:
            error("UNKNOWN_UNIT", f"unit {row['unit']!r} is not defined", "unit")
        if measure is not None and unit is not None and unit.canonical_code != measure.canonical_unit_code:
            error("UNIT_MEASURE_MISMATCH", f"{unit.code} cannot express {measure.code} (needs {measure.canonical_unit_code})", "unit")
        if status not in STATUSES:
            error("INVALID_STATUS", f"status must be one of {sorted(STATUSES)}", "status")
        try:
            start, end = parse_period(period_type, row["period"])
        except ValueError as exc:
            error("INVALID_PERIOD", str(exc), "period")
            start = end = None
        try:
            value = Decimal(row["value"].replace(",", "").strip())
            if not value.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            error("INVALID_NUMBER", f"value {row['value']!r} is not a number", "value")
            value = None
        if value is not None and value < 0:
            error("NEGATIVE_VALUE", "statistics here cannot be negative", "value")
        if sum(1 for i in report.issues if i["severity"] == "ERROR") > errors_before:
            report.rows_rejected += 1
            continue
        key = (measure.code, crop_id, area_id, period_type, start)
        canonical = value * unit.factor_to_canonical
        if key in seen and seen[key] != canonical:
            error("CONFLICTING_DUPLICATE", "the same figure appears twice in this file with different values", "value")
            report.rows_rejected += 1
            continue
        seen[key] = canonical
        _record(session, report, run, publication, dataset, raw, number, measure=measure, unit=unit, crop_id=crop_id, area_id=area_id,
                period_type=period_type, start=start, end=end, value=value, status=status,
                quality_flag=(row.get("quality_flag") or "").strip() or None, source_flag=None)
    return _finish(session, savepoint, run, publication, report, apply)


# --- FAOSTAT normalized bulk CSV --------------------------------------------------------------------------------------

def load_element_map(path: Path) -> dict[int, dict]:
    return {int(r["element_code"]): r for r in _read_csv(path)[1]}


def import_faostat(session: Session, path: Path, *, dataset_code: str, operator: str, apply: bool = False,
                   element_map: Path | None = None, version_label: str | None = None, retrieval_url: str | None = None) -> ImportReport:
    content, rows = _read_csv(path)
    report = ImportReport(mode="APPLY" if apply else "DRY_RUN")
    if not rows or FAOSTAT_COLUMNS - set(rows[0]):
        raise ImportRefused(f"{path.name} is not a FAOSTAT normalized CSV (needs {sorted(FAOSTAT_COLUMNS)})")
    source, dataset = _dataset(session, "FAOSTAT", dataset_code)
    mapping = load_element_map(element_map or REFERENCE_DIR / "faostat_element_map.csv")
    savepoint = session.begin_nested()
    try:
        started = _start(session, source, dataset, content, path=path, parser="faostat_normalized", apply=apply, operator=operator,
                         version_label=version_label or path.name, retrieval_url=retrieval_url, report=report)
    except ImportRefused:
        savepoint.rollback()
        raise
    if started is None:
        savepoint.rollback()
        return report
    publication, run = started
    measures = {m.code: m for m in session.scalars(select(Measure))}
    units = {u.code: u for u in session.scalars(select(Unit))}
    crops = {c.fao_item_code: c for c in session.scalars(select(Crop).where(Crop.fao_item_code.is_not(None)))}
    areas = {g.fao_area_code: g for g in session.scalars(select(GeoArea).where(GeoArea.fao_area_code.is_not(None)))}
    for number, row in enumerate(rows, start=2):
        report.rows_read += 1
        raw = _raw(session, run, publication, number, row)
        if raw is None:
            report.rows_duplicate += 1
            continue
        try:
            area_code, item_code, element_code, year = (int(row[c]) for c in ("Area Code", "Item Code", "Element Code", "Year"))
            value = Decimal(row["Value"]) if (row.get("Value") or "").strip() else None
        except (ValueError, InvalidOperation):
            _issue(session, report, run, raw, number, "INVALID_FAOSTAT_ROW", "ERROR", "codes, year or value are not numbers")
            report.rows_rejected += 1
            continue
        session.add(FaostatObservation(
            publication_id=publication.id, raw_observation_id=raw.id, area_code=area_code, area_m49=row.get("Area Code (M49)") or None,
            area_name=row["Area"], item_code=item_code, item_cpc=row.get("Item Code (CPC)") or None, item_name=row["Item"],
            element_code=element_code, element_name=row["Element"], year=year, unit=row["Unit"], value=value,
            flag=row.get("Flag") or None, note=row.get("Note") or None))
        session.flush()
        report.faostat_rows += 1
        mapped, crop, area = mapping.get(element_code), crops.get(item_code), areas.get(area_code)
        if value is None:
            _issue(session, report, run, raw, number, "NO_VALUE", "INFO", "kept with its flag; no value to map")
            continue
        if mapped is None or str(mapped.get("verified", "")).lower() != "true":
            _issue(session, report, run, raw, number, "UNVERIFIED_ELEMENT", "INFO",
                   f"element {element_code} has no verified mapping; kept as a FAOSTAT row only")
            continue
        if crop is None or not crop.fao_item_code_verified:
            _issue(session, report, run, raw, number, "UNVERIFIED_ITEM", "INFO",
                   f"item {item_code} ({row['Item']}) is not mapped to a crop with a verified FAO code; kept as a FAOSTAT row only")
            continue
        if area is None:
            _issue(session, report, run, raw, number, "UNKNOWN_AREA", "INFO", f"area {area_code} is not a KoroFarm area; kept as a FAOSTAT row only")
            continue
        measure, unit = measures[mapped["measure_code"]], units[mapped["unit_code"]]
        if row["Unit"].strip() != mapped["fao_unit"]:
            _issue(session, report, run, raw, number, "UNIT_MISMATCH", "ERROR",
                   f"FAOSTAT unit {row['Unit']!r} differs from the mapped {mapped['fao_unit']!r}; not converted", "Unit")
            report.rows_rejected += 1
            continue
        if value < 0:
            _issue(session, report, run, raw, number, "NEGATIVE_VALUE", "ERROR", "statistics here cannot be negative", "Value")
            report.rows_rejected += 1
            continue
        _record(session, report, run, publication, dataset, raw, number, measure=measure, unit=unit, crop_id=crop.id, area_id=area.id,
                period_type="YEAR", start=date(year, 1, 1), end=date(year, 12, 31), value=value,
                status="ESTIMATE" if (row.get("Flag") or "").strip() in ("E", "I", "M") else "FINAL",
                quality_flag=None, source_flag=(row.get("Flag") or "").strip() or None)
    return _finish(session, savepoint, run, publication, report, apply)
