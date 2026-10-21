"""Validate normalized Ministry data at the training boundary, before fitting."""
import calendar
import hashlib
import json
import math

UNITS = {"production": "tonnes", "area": "hectares", "price": "JMD/kg"}


def training_content_hash(observations):
    """v1: ingestion order by calendar/measurement, JSON keys sorted, UTF-8.

    Includes all normalized observations and their extraction/source evidence.
    Canonical ordering preserves the existing ingestion fingerprint.
    """
    try:
        if any(not isinstance(r, dict) for r in observations):
            raise ValueError("Each observation must be an object")
        ordered = sorted(observations, key=lambda r: (r['year'], r['quarter'], r['measurement']))
        canonical = json.dumps(ordered, sort_keys=True, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Observations must contain finite JSON-compatible values and reporting metadata") from exc
    return hashlib.sha256(canonical).hexdigest()


def validate_training_data(observations, quality):
    if not isinstance(observations, list) or not observations:
        raise ValueError("Training requires non-empty normalized observations")
    if not isinstance(quality, dict):
        raise ValueError("Training requires a quality report")
    documents = quality.get("documents")
    if (quality.get("sanity_checks_passed") is not True or not isinstance(documents, list)
            or not documents or any(not isinstance(d, dict) or d.get("status") != "parsed" for d in documents)):
        raise ValueError("Resolve document extraction / sanity-check errors before training")
    actual_version = training_content_hash(observations)
    if quality.get("dataset_version") != actual_version:
        raise ValueError("Dataset version mismatch: observations differ from the quality report; rerun validated ingestion")

    keys, periods = set(), set()
    counts = {m:0 for m in UNITS}
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError("Each observation must be an object")
        evidence = row.get('evidence')
        if (not row.get('source_organization') or not row.get('source_dataset')
                or not isinstance(evidence, list) or not evidence
                or any(not isinstance(e, dict) or not e.get('source_url')
                       or not e.get('local_path') or not isinstance(e.get('source_sha256'), str)
                       or len(e['source_sha256']) != 64 or not e.get('source_page')
                       or not e.get('extraction_version') for e in evidence)):
            raise ValueError('Missing source identity or extraction metadata')
        if (row.get("country") != "Jamaica" or row.get("country_code") != "JAM"
                or row.get("geography") != "national" or row.get("crop") != "iceberg_lettuce"
                or row.get("frequency") != "quarterly"):
            raise ValueError("Unsupported training scope: require Jamaica national quarterly iceberg lettuce")
        year, quarter = row.get("year"), row.get("quarter")
        if type(year) is not int or not 1 <= year <= 9999 or type(quarter) is not int or not 1 <= quarter <= 4:
            raise ValueError("Invalid reporting year or quarter")
        month = quarter * 3
        if (row.get("period") != f"{year} Q{quarter}"
                or row.get("observation_start") != f"{year}-{month-2:02d}-01"
                or row.get("observation_end") != f"{year}-{month:02d}-{calendar.monthrange(year,month)[1]:02d}"):
            raise ValueError("Observation dates do not match the reporting quarter")
        measurement = row.get("measurement")
        if not isinstance(measurement, str) or measurement not in UNITS or row.get("unit") != UNITS[measurement]:
            raise ValueError("Unsupported measurement or incorrect normalized unit")
        key = f"JAM:national:iceberg_lettuce:{measurement}:{year}:Q{quarter}"
        if row.get("id") != key:
            raise ValueError("Observation ID does not match its natural key")
        if key in keys:
            raise ValueError("Duplicate observation natural key")
        keys.add(key)
        periods.add(year*4+quarter)
        value, status = row.get("value"), row.get("status")
        if status == "validated":
            if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Validated observations require finite non-negative numeric values")
            counts[measurement] += 1
        elif status == "quarantined":
            if value is not None:
                raise ValueError("Quarantined observations must retain a null value")
        else:
            raise ValueError("Unsupported observation validation status")
    if counts["production"] == 0:
        raise ValueError("Training requires validated production observations")
    if len(periods) != max(periods)-min(periods)+1:
        raise ValueError("Missing calendar quarters must be represented explicitly before training")
    if quality.get("normalized_records") != len(observations) or quality.get("validated_counts") != counts:
        raise ValueError("Quality report observation counts do not match the dataset")
    return dict(content_hash=actual_version, canonicalization='moa-calendar-measurement-json-v1',
                observation_count=len(observations), training_cutoff=max(r['period'] for r in observations))
