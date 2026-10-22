"""Create a versioned offline artifact and identical public-statistics demo snapshot."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.agriculture.forecasting import backtest
from app.agriculture.api import annual_context
from app.agriculture.validation import validate_training_data

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/agriculture"


def train():
    observations = json.loads((DATA / "observations.json").read_text(encoding="utf-8"))
    quality = json.loads((DATA / "quality-report.json").read_text(encoding="utf-8"))
    training_manifest = validate_training_data(observations, quality)
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    source_index = {(s['url'], s['sha256']): s for s in sources}
    for row in observations:
        for evidence in row['evidence']:
            source = source_index.get((evidence['source_url'], evidence['source_sha256']))
            if source is None or source['local_path'] != evidence['local_path']:
                raise ValueError('Training source not present in preserved source manifest')
    for source in sources:
        path = (ROOT / source['local_path']).resolve()
        if not path.is_relative_to((ROOT / 'data/agriculture/raw').resolve()):
            raise ValueError('Training source path outside preserved source directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Training source content hash mismatch')
    series = []
    periods = sorted({(r["year"],r["quarter"]) for r in observations})
    # Calendar indexing is explicit: missing quarters never shift seasonal lags.
    for year, quarter in periods:
        row = dict(year=year, quarter=quarter, period=f"{year} Q{quarter}")
        for measurement, name in [("production","production_tonnes"),("price","farmgate_price_jmd_kg"),("area","area_hectares")]:
            matches = [r for r in observations if (r["year"],r["quarter"],r["measurement"]) == (year,quarter,measurement)]
            row[name] = matches[0]["value"] if matches and matches[0]["status"] == "validated" else None
        series.append(row)
    if any((b["year"]*4+b["quarter"]) - (a["year"]*4+a["quarter"]) != 1 for a,b in zip(series,series[1:])):
        raise ValueError("Calendar gaps must be represented explicitly before training")
    experiment = backtest(series)
    artifact = dict(schema_version=1, status="available", country="Jamaica", geography="national",
        crop="iceberg_lettuce", crop_label="Iceberg lettuce", dataset_version=quality["dataset_version"],
        generated_at=datetime.now(timezone.utc).isoformat(), last_ingested_at=max(s["retrieved_at"] for s in sources),
        series=series, experiment=experiment, quality=quality, sources=sources,
        training_manifest=dict(training_manifest, model_config=experiment['config']),
        annual_context=annual_context(),
        limitations=["Experimental national production forecast — not a verified shortage prediction.",
            "Historical publication dates and revision vintages are unavailable. This is a retrospective latest-vintage simulation, not measured real-time performance.",
            "2016 Q3 production is quarantined because the official production and combined tables disagree; no value is imputed.",
            "The latest linked observation is 2025 Q4. The 2026 Q1 estimate is historical, not a forecast for the current quarter.",
            "Only 20 quarterly evaluation targets; performance may change under future weather, market or reporting conditions.",
            "No calibrated uncertainty interval is available. Production and observed price movements do not establish causation.",
            "National estimates are separate from synthetic farm inventories, commitments and accepted supply."])
    fingerprint = dict(artifact)
    fingerprint.pop("generated_at")
    artifact["artifact_version"] = hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
    output = json.dumps(artifact, indent=2, allow_nan=False) + "\n"
    artifact_dir = DATA / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    version_path = artifact_dir / f'{artifact["artifact_version"]}.json'
    if not version_path.exists():
        version_path.write_text(output,encoding="utf-8")
    else:
        output = version_path.read_text(encoding="utf-8")
    # Atomic replacement prevents partial artifacts being served during refresh.
    for path in [DATA / "intelligence.json", ROOT / "src/frontend/public/agriculture/intelligence.json"]:
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(output,encoding="utf-8")
        temporary.replace(path)
    print(json.dumps(dict(metrics=experiment["metrics"], selected=experiment["selected_model"],forecast=experiment["forecast"]),indent=2))
    return artifact


if __name__ == "__main__":
    train()
