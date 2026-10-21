"""Strict, text-layer extraction for the reviewed Ministry table layouts (no OCR)."""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data/agriculture"
VERSION = "moa-iceberg-text-v1"
# These spelling variants label the same dedicated iceberg row in overlapping
# Ministry tables; OTHER LETTUCE is explicitly not mapped.
ALIASES = {"ICEBURG LETTUCE", "ICEBURGH LETTUCE", "ICEBERG LETTUCE"}
UNITS = {"production": "tonnes", "area": "hectares", "price": "JMD/kg"}
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def parse_row(line, count):
    match = re.fullmatch(r"(ICEBURG(?:H)? LETTUCE|ICEBERG LETTUCE)\s+(.+)", line)
    if not match or match[1] not in ALIASES:
        raise ValueError(f"Unmapped iceberg row: {line}")
    tokens = match[2].split()
    if len(tokens) != count or any(not re.fullmatch(NUMBER, t) for t in tokens):
        raise ValueError(f"Unexpected numeric columns: {line}")
    return match[1], [float(t.replace(",", "")) for t in tokens]


def extract(source):
    path = ROOT / source["local_path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("Source checksum mismatch")
    rows, annual_checks = [], []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            lines = [s for s in text.splitlines() if any(s.startswith(a + " ") for a in ALIASES)]
            if not lines:
                continue  # Some documents have a footer-only second page.
            if len(lines) != 1:
                raise ValueError("Ambiguous iceberg row")
            year = source["year"]
            if not re.search(rf"QUARTER\s+{year}\b", text, re.I):
                raise ValueError("Reporting year does not match index label")
            kind = source["kind"]
            required = ["HECTARE", "TONNE", "$/KG"] if kind == "combined" else [{"production": "TONNE", "area": "HECTARE", "price": "$/KG"}[kind]]
            if any(unit not in text.upper() for unit in required):
                raise ValueError("Expected measurement unit not found")
            label, values = parse_row(lines[0], 3 if kind == "combined" else 5)
            if kind == "combined":
                match = re.search(r"([1-4])(?:st|nd|rd|th)\s+QUARTER", text, re.I)
                if not match:
                    raise ValueError("Missing reporting quarter")
                cells = [(int(match[1]), m, v) for m, v in zip(["area", "production", "price"], values)]
            else:
                # Confirm the column order rather than assuming a reversed layout.
                if not re.search(r"1(?:st|ST)\s+Quarter.*2nd\s+Quarter.*3rd\s+Quarter.*4th\s+Quarter", text, re.I):
                    raise ValueError("Unexpected quarter columns")
                cells = [(q, kind, values[q-1]) for q in range(1, 5)]
                if kind in {"area", "production"}:
                    delta = sum(values[:4]) - values[4]
                    annual_checks.append(dict(year=year, measurement=kind, quarterly_sum=sum(values[:4]),
                        annual_value=values[4], difference=delta, source_url=source["url"],
                        status="exact" if delta == 0 else "within_rounding_tolerance" if abs(delta) <= 2.5 else "inconsistent",
                        tolerance=2.5))
            for q, measurement, value in cells:
                rows.append(dict(year=year, quarter=q, measurement=measurement, value=value,
                    original_crop_label=label, original_unit={"production": "TONNE", "area": "HECTARE", "price": "$/KG"}[measurement],
                    unit=UNITS[measurement], source_url=source["url"], source_sha256=source["sha256"],
                    local_path=source["local_path"], source_kind=kind, source_page=page_number,
                    source_row=lines[0], publication_date=source["publication_date"],
                    http_last_modified=source["http_last_modified"], ingested_at=source["retrieved_at"],
                    classification="official_estimate", revision_status="unknown",
                    source_annotation="Asterisk present; meaning not established" if "*" in text else None,
                    extraction_version=VERSION))
    expected = 12 if source["kind"] == "combined" else 4
    if len(rows) != expected:
        raise ValueError(f"Expected {expected} cells, got {len(rows)}")
    return rows, annual_checks


def build_dataset():
    sources = json.loads((DATA / "sources.json").read_text())
    # Preserve old versions in manifest, but use the latest fetched version per URL.
    latest = {s["url"]: s for s in sources}
    candidates, annual, documents = [], [], []
    for source in latest.values():
        try:
            rows, checks = extract(source)
            candidates.extend(rows)
            annual.extend(checks)
            documents.append(dict(url=source["url"], status="parsed", cells=len(rows)))
        except Exception as exc:
            documents.append(dict(url=source["url"], status="quarantined", reason=str(exc)))
    grouped = defaultdict(list)
    for row in candidates:
        grouped[(row["year"], row["quarter"], row["measurement"])].append(row)
    normalized, conflicts = [], []
    for (year, quarter, measurement), evidence in sorted(grouped.items()):
        # Prefer combined documents only when their overlapping cells agree exactly.
        chosen = sorted(evidence, key=lambda r: r["source_kind"] != "combined")[0]
        conflict = len({r["value"] for r in evidence}) > 1
        bad_annual = any(c["year"] == year and c["measurement"] == measurement and c["status"] == "inconsistent" for c in annual)
        status = "quarantined" if conflict or bad_annual else "validated"
        key = f"JAM:national:iceberg_lettuce:{measurement}:{year}:Q{quarter}"
        record = dict(id=key, country="Jamaica", country_code="JAM", geography="national",
            crop="iceberg_lettuce", frequency="quarterly", period=f"{year} Q{quarter}",
            observation_start=f"{year}-{(quarter-1)*3+1:02d}-01",
            observation_end=f"{year}-{quarter*3:02d}-" + ("30" if quarter in (2,3) else "31"),
            year=year, quarter=quarter, measurement=measurement, unit=UNITS[measurement],
            value=None if status == "quarantined" else chosen["value"], status=status,
            source_organization="Jamaica Ministry of Agriculture, Fisheries and Mining",
            source_dataset="All-island quarterly crop estimates",
            mapping_provenance="Explicit Ministry iceberg spelling aliases only; other lettuce excluded.",
            evidence=evidence)
        normalized.append(record)
        if status == "quarantined":
            conflicts.append(dict(id=key, period=record["period"], measurement=measurement,
                reason="Conflicting official source values" if conflict else "Annual reconciliation exceeds rounding tolerance",
                values=[dict(value=r["value"], url=r["source_url"], page=r["source_page"]) for r in evidence]))
    gaps = [f"{year} Q{q}: {m}" for year in range(2016,2026) for q in range(1,5) for m in UNITS
            if not any(r["year"] == year and r["quarter"] == q and r["measurement"] == m and r["status"] == "validated" for r in normalized)]
    # These checks come from the brief, but acceptance uses values extracted from originals.
    sanity = {(2025,1,"production"):5089, (2025,2,"production"):4616,
              (2025,3,"production"):3718, (2025,4,"production"):3110,
              (2025,2,"price"):294.28, (2025,4,"price"):1150.02}
    sanity_passed = all(any((r["year"],r["quarter"],r["measurement"]) == key and r["value"] == value and r["status"] == "validated" for r in normalized) for key,value in sanity.items())
    version = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    report = dict(dataset_version=version, extraction_version=VERSION, documents=documents,
        source_versions=len(sources), extracted_cells=len(candidates), normalized_records=len(normalized),
        validated_counts={m:sum(r["measurement"] == m and r["status"] == "validated" for r in normalized) for m in UNITS},
        conflicts=conflicts, gaps=gaps, annual_checks=annual, sanity_checks_passed=sanity_passed,
        notes=["Annual/quarter sums may differ through independent rounding; tolerance is 2.5 displayed units (five rounded cells).",
               "Annual prices are not summed or assumed to be unweighted averages.",
               "No 2026 records linked on the four inspected indexes.",
               "Historical publication dates and revision vintages are unknown; no real-time availability claim."])
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "observations.json").write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    (DATA / "quality-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
