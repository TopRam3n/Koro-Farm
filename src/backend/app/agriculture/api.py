"""Read-only serving of an offline artifact. No training, scraping or mutations."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from .schema import IntelligenceArtifact

router = APIRouter(prefix="/agricultural-intelligence", tags=["agricultural-intelligence"])
ARTIFACT = Path(__file__).resolve().parents[4] / "data/agriculture/intelligence.json"
ANNUAL = Path(__file__).resolve().parents[4] / "data/agriculture/faostat/qcl-jamaica-2016-2025.json"


def annual_context(item_code="372"):
    try:
        artifact = json.loads(ANNUAL.read_text(encoding="utf-8"))
        records = artifact["records"]
        if artifact.get("schema_version") != 1 or artifact.get("frequency") != "annual" or any(r.get("frequency") != "annual" or r.get("quarter") is not None for r in records):
            raise ValueError("Invalid annual artifact")
        selected = [r for r in records if r["item_code"] == item_code]
        if not selected:
            raise HTTPException(404, detail="Unsupported FAOSTAT item; no verified observations")
        return dict(status="available", source="FAOSTAT", domain=artifact["domain"],
            frequency="annual", country="Jamaica", item_code=item_code,
            item_label=selected[0]["original_item"], mapped_ministry_crop=None,
            records=selected, validation=artifact["validation"],
            dataset_version=artifact["dataset_version"], source_url=artifact["source_url"],
            retrieved_at=artifact["retrieved_at"], access_method=artifact["access_method"],
            limitations=artifact["limitations"])
    except (OSError, ValueError, KeyError, TypeError):
        return dict(status="unavailable", frequency="annual", records=[],
            reason="Validated FAOSTAT annual artifact missing or invalid")


@router.get("/faostat")
def faostat_intelligence(item_code: str = "372"):
    result = annual_context(item_code)
    if result["status"] != "available":
        raise HTTPException(503, detail=result["reason"])
    return result


@router.get("")
def intelligence(crop: str = "iceberg_lettuce"):
    if crop != "iceberg_lettuce":
        raise HTTPException(404, detail="Unsupported or unmapped crop; no forecast available")
    try:
        artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        IntelligenceArtifact.model_validate(artifact)
        return artifact
    except (OSError, ValueError):
        raise HTTPException(503, detail="Agricultural intelligence unavailable — validated offline artifact missing or invalid")
