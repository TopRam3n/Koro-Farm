"""Verify persisted Checkpoint 1 evidence without network or database mutations."""
import hashlib
import json
from pathlib import Path

from src.backend.app.agriculture.faostat_client import acquire_jamaica, atomic_json

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/agriculture"


def validate():
    sources = json.loads((DATA / "sources.json").read_text())
    for source in sources:
        if hashlib.sha256((ROOT/source["local_path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Ministry original checksum mismatch")
    quality = json.loads((DATA / "quality-report.json").read_text())
    observations = json.loads((DATA / "observations.json").read_text())
    if not quality["sanity_checks_passed"] or any(d["status"] != "parsed" for d in quality["documents"]):
        raise ValueError("Ministry extraction validation failed")
    if len(observations) != len({r["id"] for r in observations}):
        raise ValueError("Duplicate Ministry observation keys")
    if any(r["status"] != "validated" and r["value"] is not None for r in observations):
        raise ValueError("Quarantined Ministry cell has a usable value")
    annual = acquire_jamaica()
    annual_dir = DATA / "faostat"
    manifest = json.loads((annual_dir / "qcl-jamaica-2016-2025-source.json").read_text())
    for receipt in [manifest, *manifest["contracts"], *manifest["metadata_sources"]]:
        if hashlib.sha256((annual_dir / receipt["local_file"]).read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError("FAOSTAT source or reviewed-contract checksum mismatch")
    if any(r["frequency"] != "annual" or r["quarter"] is not None or r["mapped_ministry_crop"] is not None for r in annual["records"]):
        raise ValueError("Annual and quarterly classifications were mixed")
    serving = json.loads((DATA / "intelligence.json").read_text())
    if serving["annual_context"]["dataset_version"] != annual["dataset_version"]:
        raise ValueError("Serving artifact contains a stale annual context; rerun training")
    if serving["dataset_version"] != quality["dataset_version"]:
        raise ValueError("Serving artifact contains a stale Ministry dataset")
    if (DATA / "intelligence.json").read_bytes() != (ROOT / "src/frontend/public/agriculture/intelligence.json").read_bytes():
        raise ValueError("Backend and explicit demo snapshots differ")
    result = dict(status="passed", ministry_original_pdfs=len(sources),
        ministry_normalized_cells=len(observations), ministry_validated_counts=quality["validated_counts"],
        ministry_coverage="2016 Q1 through 2025 Q4", quarantined=quality["conflicts"],
        faostat_access=annual["access_method"], faostat_validation=annual["validation"],
        quarterly_dataset_version=quality["dataset_version"], annual_dataset_version=annual["dataset_version"],
        serving_artifact_version=serving["artifact_version"],
        limitations=["2016 Q3 Ministry production quarantined pending source clarification",
            "2025 FAOSTAT observations not returned; per-series gaps preserved",
            "Historical publication/revision vintages unavailable; forecasts remain retrospective",
            "FAOSTAT estimated/imputed/external classifications remain source flags, not independently verified measurements"])
    atomic_json(DATA / "checkpoint-1.json", result)
    return result


if __name__ == "__main__":
    result = validate()
    print(json.dumps(dict(status=result["status"], ministry=result["ministry_validated_counts"],
        faostat_observations=result["faostat_validation"]["observations"],
        faostat_years=result["faostat_validation"]["years"], limitations=result["limitations"]),indent=2))
