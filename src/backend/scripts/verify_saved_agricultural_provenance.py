"""Read-only verification of preserved snapshot consistency; never fits a model."""
import hashlib
import json
from pathlib import Path

from app.agriculture.schema import IntelligenceArtifact
from app.agriculture.validation import validate_training_data

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / 'data/agriculture'


def verify():
    artifact_bytes = (DATA / 'intelligence.json').read_bytes()
    artifact = json.loads(artifact_bytes)
    IntelligenceArtifact.model_validate(artifact)
    rows = json.loads((DATA / 'observations.json').read_text(encoding='utf-8'))
    quality = json.loads((DATA / 'quality-report.json').read_text(encoding='utf-8'))
    manifest = validate_training_data(rows, quality)
    assert artifact['dataset_version'] == manifest['content_hash'], 'Saved dataset identity mismatch'
    sources = json.loads((DATA / 'sources.json').read_text(encoding='utf-8'))
    assert sources == artifact['sources'], 'Saved source manifest mismatch'
    index = {(s['url'], s['sha256'], s['local_path']) for s in sources}
    for source in sources:
        path = (ROOT / source['local_path']).resolve()
        assert path.is_relative_to((DATA / 'raw').resolve()), 'Source path outside raw directory'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256'], 'Source PDF hash mismatch'
    for row in rows:
        assert all((e['source_url'], e['source_sha256'], e['local_path']) in index for e in row['evidence']), 'Unlinked evidence'
    names = {'production': 'production_tonnes', 'price': 'farmgate_price_jmd_kg', 'area': 'area_hectares'}
    for period in artifact['series']:
        for measurement, field in names.items():
            matches = [r for r in rows if r['period'] == period['period'] and r['measurement'] == measurement]
            assert len(matches) == 1
            row = matches[0]
            assert period[field] == (row['value'] if row['status'] == 'validated' else None), 'Saved series mismatch'
    assert len(artifact['series']) == len({r['period'] for r in rows})
    fingerprint = {k:v for k,v in artifact.items() if k not in ('generated_at', 'artifact_version')}
    assert hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest() == artifact['artifact_version'], 'Artifact fingerprint mismatch'
    assert (ROOT / 'src/frontend/public/agriculture/intelligence.json').read_bytes() == artifact_bytes
    return dict(status='snapshot_consistency_verified', source_pdfs=len(sources), observations=len(rows),
        dataset_content_hash=manifest['content_hash'], artifact_sha256=hashlib.sha256(artifact_bytes).hexdigest(),
        training_cutoff=artifact['experiment']['forecast']['data_cutoff'], model_config=artifact['experiment']['config'],
        limitation='Checks preserved bytes, manifest links and series consistency only. The legacy artifact has no contemporaneous signed training-input manifest, code/environment capture or serialized fitted coefficients. Historical execution provenance and publication-time availability cannot be certified retroactively.')


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
