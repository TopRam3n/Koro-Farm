"""Failure-injection tests use temporary copies; never publish/retrain the demo."""
import hashlib
import json
from unittest.mock import Mock

import pytest

from src.backend.scripts import train_agricultural_forecast as trainer
from app.agriculture.validation import validate_training_data


@pytest.fixture
def training_copy(tmp_path, monkeypatch):
    for name in ("observations.json", "quality-report.json", "sources.json"):
        (tmp_path / name).write_bytes((trainer.DATA / name).read_bytes())
    monkeypatch.setattr(trainer, "DATA", tmp_path)
    learner = Mock(side_effect=AssertionError("Learner must not run on invalid input"))
    monkeypatch.setattr(trainer, "backtest", learner)
    return tmp_path, learner


def test_changed_observations_are_rejected_before_fitting(training_copy):
    path, learner = training_copy
    observations = json.loads((path / "observations.json").read_text(encoding="utf-8"))
    row = next(r for r in observations if r["measurement"] == "production" and r["status"] == "validated")
    row["value"] += 100000  # Test-only corruption; quality report remains unchanged.
    (path / "observations.json").write_text(json.dumps(observations), encoding="utf-8")
    with pytest.raises(ValueError, match="Dataset version mismatch"):
        trainer.train()
    learner.assert_not_called()
    assert not (path / "artifacts").exists()


def read_dataset(path):
    observations = json.loads((path / "observations.json").read_text(encoding="utf-8"))
    quality = json.loads((path / "quality-report.json").read_text(encoding="utf-8"))
    return observations, quality


def update_identity(observations, quality):
    quality["dataset_version"] = hashlib.sha256(
        json.dumps(sorted(observations, key=lambda r: (r['year'], r['quarter'], r['measurement'])), sort_keys=True).encode("utf-8")
    ).hexdigest()


def test_current_dataset_passes_and_preserves_disputed_quarter(training_copy):
    observations, quality = read_dataset(training_copy[0])
    validate_training_data(observations, quality)
    disputed = next(r for r in observations if r["measurement"] == "production"
                    and r["year"] == 2016 and r["quarter"] == 3)
    assert disputed["status"] == "quarantined"
    assert disputed["value"] is None


@pytest.mark.parametrize("field,value,message", [
    ("unit", "kg", "incorrect normalized unit"),
    ("frequency", "annual", "Unsupported training scope"),
    ("crop", "lettuce", "Unsupported training scope"),
    ("quarter", 5, "Invalid reporting"),
    ("observation_end", "2016-03-30", "dates do not match"),
    ("id", "incorrect", "natural key"),
    ("value", -1, "finite non-negative"),
    ("value", True, "finite non-negative"),
    ("value", None, "finite non-negative"),
    ("value", float("nan"), "finite JSON"),
    ("status", "unchecked", "validation status"),
])
def test_semantic_corruption_rejected_even_with_matching_hash(training_copy, field, value, message):
    observations, quality = read_dataset(training_copy[0])
    row = next(r for r in observations if r["measurement"] == "production" and r["status"] == "validated")
    row[field] = value
    update_identity(observations, quality)
    with pytest.raises(ValueError, match=message):
        validate_training_data(observations, quality)


def test_duplicate_natural_key_rejected(training_copy):
    observations, quality = read_dataset(training_copy[0])
    observations.append(dict(observations[0]))
    update_identity(observations, quality)
    with pytest.raises(ValueError, match="Duplicate observation"):
        validate_training_data(observations, quality)


def test_quarantined_value_cannot_enter_training(training_copy):
    observations, quality = read_dataset(training_copy[0])
    next(r for r in observations if r["status"] == "quarantined")["value"] = 2525
    update_identity(observations, quality)
    with pytest.raises(ValueError, match="Quarantined observations"):
        validate_training_data(observations, quality)


def test_quality_counts_must_match(training_copy):
    observations, quality = read_dataset(training_copy[0])
    quality["validated_counts"]["production"] += 1
    with pytest.raises(ValueError, match="counts do not match"):
        validate_training_data(observations, quality)


def test_missing_calendar_quarter_rejected(training_copy):
    observations, quality = read_dataset(training_copy[0])
    observations = [r for r in observations if not (r["year"] == 2017 and r["quarter"] == 2)]
    update_identity(observations, quality)
    with pytest.raises(ValueError, match="Missing calendar quarters"):
        validate_training_data(observations, quality)


def test_valid_input_reaches_learner_without_publishing(training_copy):
    path, learner = training_copy
    with pytest.raises(AssertionError, match='Learner must not run'):
        trainer.train()
    series = learner.call_args.args[0]
    assert len(series) == 40
    assert sum(r['production_tonnes'] is not None for r in series) == 39
    assert next(r for r in series if r['period'] == '2016 Q3')['production_tonnes'] is None
    assert not (path / 'artifacts').exists()


def test_unlinked_source_manifest_rejected_before_fitting(training_copy):
    path, learner = training_copy
    sources = json.loads((path / 'sources.json').read_text())
    sources[0]['sha256'] = 'a' * 64
    (path / 'sources.json').write_text(json.dumps(sources))
    with pytest.raises(ValueError, match='preserved source manifest'):
        trainer.train()
    learner.assert_not_called()


def test_changed_raw_source_rejected_before_fitting(training_copy, monkeypatch):
    from pathlib import Path
    _, learner = training_copy
    original = Path.read_bytes
    def altered_bytes(path):
        if path.suffix == '.pdf':
            return b'test-only corrupted source PDF'
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', altered_bytes)
    with pytest.raises(ValueError, match='source content hash mismatch'):
        trainer.train()
    learner.assert_not_called()
