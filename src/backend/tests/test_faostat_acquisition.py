"""Offline tests use cached original FAO responses; no network dependency."""
import hashlib
import json

import pytest

from app.agriculture import api
from app.agriculture.faostat import normalize_rows
from app.agriculture.faostat_client import DATA, FaostatClient, acquire_jamaica


def test_genuine_source_normalizes_idempotently_without_mixing_frequencies():
    class NoNetwork:
        def _read(self, *args, **kwargs):
            raise AssertionError("Cached imports must not require credentials/network")
    result = acquire_jamaica(client=NoNetwork())
    path = DATA / "qcl-jamaica-2016-2025.json"
    before = path.read_bytes()
    again = acquire_jamaica(client=NoNetwork())
    assert before == path.read_bytes()
    assert result == again
    assert len(result["records"]) == 1496
    validation = result["validation"]
    assert validation["years"] == list(range(2016,2025))
    assert validation["missing_requested_years"] == [2025]
    assert validation["counts_by_measurement"] == {"Production":938,"Area harvested":558}
    assert validation["duplicate_rows"] == validation["rejected_rows"] == 0
    rows = result["records"]
    assert len({r["id"] for r in rows}) == len(rows)
    assert all(r["frequency"] == "annual" and r["quarter"] is None and r["mapped_ministry_crop"] is None for r in rows)
    assert all(r["country"] == "Jamaica" for r in rows)
    assert all(r["source_sha256"] == result["source_sha256"] for r in rows)
    lettuce = [r for r in rows if r["original_item"] == "Lettuce and chicory"]
    assert len(lettuce) == 18
    assert {r["item_code"] for r in lettuce} == {"372"}
    assert validation["flags"] == {"A":949,"E":195,"I":338,"X":14}


def test_original_source_and_documentation_checksums():
    manifest = json.loads((DATA / "qcl-jamaica-2016-2025-source.json").read_text())
    for receipt in [manifest, *manifest["contracts"], *manifest["metadata_sources"]]:
        assert hashlib.sha256((DATA / receipt["local_file"]).read_bytes()).hexdigest() == receipt["sha256"]
    spec = next(c for c in manifest["contracts"] if c["url"].endswith("faostat_openapi.yaml"))
    text = (DATA / spec["local_file"]).read_text()
    assert "/{lang}/data/{domain_code}" in text and "faostatservices.fao.org/api/v1" in text
    # Receipts contain no credential responses/headers.
    assert '"Authorization"' not in json.dumps(manifest)
    assert '"token"' not in json.dumps(manifest)


def test_tampered_cache_fails_before_import(tmp_path):
    manifest = json.loads((DATA / "qcl-jamaica-2016-2025-source.json").read_text())
    file = tmp_path / manifest["local_file"]
    file.parent.mkdir(parents=True)
    file.write_text('{"data":[]}')
    (tmp_path / "qcl-jamaica-2016-2025-source.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="checksum"):
        acquire_jamaica(directory=tmp_path)


def test_annual_api_preserves_category_and_supports_missing_state(client, tmp_path, monkeypatch):
    result = client.get("/agricultural-intelligence/faostat")
    assert result.status_code == 200
    context = result.json()
    assert context["frequency"] == "annual" and context["item_label"] == "Lettuce and chicory"
    assert context["mapped_ministry_crop"] is None and len(context["records"]) == 18
    assert context["validation"]["observations"] == 1496
    assert client.get("/agricultural-intelligence/faostat?item_code=nonexistent").status_code == 404
    assert client.post("/agricultural-intelligence/faostat").status_code == 405
    monkeypatch.setattr(api,"ANNUAL",tmp_path / "missing.json")
    assert client.get("/agricultural-intelligence/faostat").status_code == 503


def test_source_flag_missing_value_and_conflicts_remain_explicit():
    row = dict(Area="Jamaica",Item="Test-only category",Element="Production",Year="2020",Unit="t",Value="0",Flag="E")
    row["Item Code"] = "999"
    result = normalize_rows([row,dict(row,Value=None)],"https://www.fao.org/faostat/","QCL","test-checksum")
    assert result["records"][0]["value"] == 0
    assert result["records"][0]["flag"] == "E"
    assert len(result["rejected"]) == 1
    with pytest.raises(ValueError,match="Conflicting duplicate"):
        normalize_rows([row,dict(row,Value="1")],"https://www.fao.org/faostat/","QCL","test-checksum")


def test_api_transport_uses_memory_token_and_does_not_disclose_it():
    from urllib.error import HTTPError
    class Response:
        headers = {}
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return self.body
    calls = []
    def opener(request, timeout):
        calls.append(request)
        if request.full_url.endswith("auth/guest"):
            return Response(b'{"token":"TEST-ONLY-SECRET"}')
        assert request.get_header("Authorization") == "Bearer TEST-ONLY-SECRET"
        return Response(b'{"data":[],"metadata":{}}')
    client = FaostatClient(opener=opener)
    client.get_json("en/codes/area/QCL/")
    client.get_json("en/codes/element/QCL/")
    assert len(calls) == 3  # One handshake, then two authenticated reads.
    def denied(request,timeout):
        raise HTTPError(request.full_url,403,"Forbidden",{},None)
    with pytest.raises(RuntimeError) as exc:
        FaostatClient(token="TEST-ONLY-SECRET",opener=denied).get_json("en/codes/area/QCL/")
    assert "TEST-ONLY-SECRET" not in str(exc.value)
