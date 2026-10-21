"""Reproducible official normalized CSV ingestion; no undocumented API paths.

FAOSTAT remains annual and separately namespaced. Items are never silently
mapped to Ministry iceberg lettuce. No input rows enter quarterly modelling.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.parse import urlparse


def import_annual_csv(path: Path, source_url: str, domain: str):
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    required = {"Area", "Item Code", "Item", "Element", "Year", "Unit", "Value"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(f"Expected normalized FAOSTAT CSV columns: {sorted(required)}")
    return normalize_rows(reader, source_url, domain, checksum, first_line=2)


def normalize_rows(rows, source_url, domain, checksum, first_line=1):
    if domain not in {"QCL", "PP"}:
        raise ValueError("Only reviewed domain identifiers QCL and PP are supported")
    host = urlparse(source_url).hostname or ""
    if urlparse(source_url).scheme != "https" or not (host == "fao.org" or host.endswith(".fao.org")):
        raise ValueError("An official HTTPS FAO source URL is required")
    records = {}
    rejected = []
    for line, row in enumerate(rows,first_line):
        if row["Area"] != "Jamaica":
            continue
        if row["Value"] is None or str(row["Value"]).strip() == "":
            rejected.append(dict(line=line,reason="Missing value; not zero"))
            continue
        try:
            year, value = int(row["Year"]), float(row["Value"])
            if not 1961 <= year <= 2100 or value < 0 or not math.isfinite(value):
                raise ValueError("Invalid year/value")
        except ValueError as exc:
            rejected.append(dict(line=line, reason=str(exc)))
            continue
        key = f'FAOSTAT:{domain}:Jamaica:{row["Item Code"]}:{row["Element"]}:{year}:{row["Unit"]}'
        record = dict(id=key, source="FAOSTAT", domain=domain, country="Jamaica", geography="national",
            original_item=row["Item"], item_code=row["Item Code"], mapped_ministry_crop=None,
            measurement=row["Element"], frequency="annual", year=year, quarter=None,
            value=value, unit=row["Unit"], flag=row.get("Flag"), note=row.get("Note"),
            flag_description=row.get("Flag Description"), element_code=row.get("Element Code"),
            item_coding_system="FAO" if row.get("Domain Code") else "as supplied in official file",
            observation_start=f"{year}-01-01", observation_end=f"{year}-12-31",
            normalized_measurement={"Production":"production","Area harvested":"area"}.get(row["Element"]),
            normalized_unit={"t":"tonnes","ha":"hectares"}.get(row["Unit"]),
            normalized_value=value if row["Unit"] in {"t","ha"} else None,
            status="validated", classification=row.get("Flag Description") or "Source classification unspecified",
            source_url=source_url, source_sha256=checksum, source_line=line, publication_date=None)
        if key in records and records[key]["value"] != value:
            raise ValueError(f"Conflicting duplicate FAOSTAT observation {key}")
        records.setdefault(key, record)
    return dict(source_url=source_url, source_sha256=checksum, domain=domain,
        records=list(records.values()), rejected=rejected,
        limitations=["Annual FAOSTAT data is not a quarterly observation or a Ministry crop mapping."])


def write_import(path, source_url, domain, destination):
    result = import_annual_csv(Path(path), source_url, domain)
    Path(destination).parent.mkdir(parents=True,exist_ok=True)
    Path(destination).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return result
