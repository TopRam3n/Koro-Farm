"""Current official FAOSTAT API adapter, isolated from operational databases.

Contract: https://www.fao.org/faostat/en/docs/faostat_openapi.yaml
Anonymous guest handshake follows the official FAOSTATAPIClient.js. Personal
bearer tokens can instead be supplied through FAOSTAT_ACCESS_TOKEN. Tokens are
kept in memory and never persisted in source manifests or frontend artifacts.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.agriculture.faostat import normalize_rows

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data/agriculture/faostat"
API = "https://faostatservices.fao.org/api/v1/"
PORTAL = "https://www.fao.org/faostat/en/"
CONTRACTS = {
    "openapi.yaml": "docs/faostat_openapi.yaml",
    "api-client.js": "src/js/FAOSTATAPIClient.js",
    "developer-portal.hbs": "src/js/templates/developer-portal.hbs",
    "developer-portal-view.js": "src/js/views/developer-portal-view.js",
}


def atomic_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


class FaostatClient:
    def __init__(self, token=None, opener=urlopen):
        self._token = token or os.getenv("FAOSTAT_ACCESS_TOKEN")
        self.auth_method = "personal_bearer" if self._token else "official_browser_guest"
        self._opener = opener

    def _read(self, url, authenticated=True):
        headers = {"User-Agent": "Mozilla/5.0 (KoroFarm agricultural statistics ingestion)",
                   "Referer": PORTAL, "Origin": "https://www.fao.org"}
        if authenticated:
            if not self._token:
                body, _ = self._read(API + "auth/guest", authenticated=False)
                self._token = json.loads(body).get("token")
                if not isinstance(self._token, str) or not self._token:
                    raise ValueError("FAOSTAT guest handshake returned no token")
            headers["Authorization"] = "Bearer " + self._token
        for attempt in range(2):
            try:
                with self._opener(Request(url, headers=headers), timeout=60) as response:
                    return response.read(), response.headers.get("Last-Modified")
            except HTTPError as exc:
                if exc.code in {429, 502, 503, 504} and attempt == 0:
                    time.sleep(1)
                    continue
                raise RuntimeError(f"FAOSTAT HTTP {exc.code} at {url}; provide a valid personal FAOSTAT_ACCESS_TOKEN if guest access is restricted") from None
            except (URLError, TimeoutError):
                raise RuntimeError(f"FAOSTAT network failure at {url}") from None

    def get_json(self, endpoint, params=None):
        url = API + endpoint + ("?" + urlencode(params) if params else "")
        body, modified = self._read(url)
        parsed = json.loads(body)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("data"), list):
            raise ValueError("Unexpected FAOSTAT response schema")
        return parsed, body, dict(url=url, http_last_modified=modified)


def acquire_jamaica(start=2016, end=2025, refresh=False, directory=DATA, client=None):
    if not 1961 <= start <= end <= datetime.now(timezone.utc).year:
        raise ValueError("Invalid annual year range")
    client = client or FaostatClient()
    directory = Path(directory)
    raw = directory / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / f"qcl-jamaica-{start}-{end}-source.json"
    if manifest_path.exists() and not refresh:
        manifest = json.loads(manifest_path.read_text())
        cached = directory / manifest["local_file"]
        if hashlib.sha256(cached.read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("FAOSTAT cached source checksum mismatch")
        payload = json.loads(cached.read_bytes())
    else:
        contracts = []
        for name, relative in CONTRACTS.items():
            body, _ = client._read(PORTAL + relative, authenticated=False)
            # Preserve each reviewed documentation version rather than overwrite it.
            digest = hashlib.sha256(body).hexdigest()
            path = raw / f"{digest[:12]}-{name}"
            path.write_bytes(body)
            contracts.append(dict(url=PORTAL+relative, sha256=digest, local_file=path.relative_to(directory).as_posix()))
        metadata_sources = []
        def fetch_metadata(endpoint):
            result, body, receipt = client.get_json(endpoint)
            digest = hashlib.sha256(body).hexdigest()
            path = raw / (digest[:16] + "-metadata.json")
            path.write_bytes(body)
            metadata_sources.append(dict(**receipt,sha256=digest,local_file=path.relative_to(directory).as_posix()))
            return result["data"]
        areas = fetch_metadata("en/codes/area/QCL/")
        jamaica = [r for r in areas if r.get("label") == "Jamaica" and r.get("aggregate_type") == "0"]
        if len(jamaica) != 1:
            raise ValueError("Could not unambiguously resolve Jamaica's official area code")
        elements = fetch_metadata("en/codes/element/QCL/")
        wanted = {}
        for label in ("Area harvested", "Production Quantity"):
            matches = [r for r in elements if r.get("label") == label and r.get("aggregate_type") == "0"]
            if len(matches) != 1:
                raise ValueError("FAOSTAT QCL measurement codes changed; review official metadata")
            wanted[str(matches[0]["code"])] = label
        fetch_metadata("en/bulkdownloads/QCL/")
        params = dict(area=str(jamaica[0]["code"]), element=",".join(wanted),
                      year=",".join(str(y) for y in range(start,end+1)), output_type="objects")
        payload, body, receipt = client.get_json("en/data/QCL", params)
        digest = hashlib.sha256(body).hexdigest()
        path = raw / f"qcl-jamaica-{start}-{end}-{digest[:12]}.json"
        path.write_bytes(body)
        manifest = dict(**receipt, domain="QCL", area_code=str(jamaica[0]["code"]),
            requested_years=list(range(start,end+1)), query=params, auth_method=client.auth_method,
            retrieved_at=datetime.now(timezone.utc).isoformat(), publication_date=None,
            sha256=digest, local_file=path.relative_to(directory).as_posix(),
            contracts=contracts, metadata_sources=metadata_sources)
        atomic_json(manifest_path, manifest)
    rows = payload["data"]
    expected_years = set(range(start,end+1))
    for row in rows:
        if row.get("Domain Code") != "QCL" or row.get("Area") != "Jamaica" or str(row.get("Area Code")) != manifest["area_code"]:
            raise ValueError("FAOSTAT returned a row outside the requested domain/country")
        code = str(row.get("Element Code"))
        expected = {"5312":("Area harvested","ha"), "5510":("Production","t"),
                    "5513":("Production","1000 No")}.get(code)
        if expected is None or (row.get("Element"), row.get("Unit")) != expected:
            raise ValueError("FAOSTAT measurement/unit mismatch")
        if int(row["Year"]) not in expected_years:
            raise ValueError("FAOSTAT returned an unrequested reporting year")
    normalized = normalize_rows(rows,manifest["url"],"QCL",manifest["sha256"])
    if normalized["rejected"] or not normalized["records"]:
        raise ValueError("Resolve rejected or empty FAOSTAT dataset before publishing")
    records = normalized["records"]
    years = sorted({r["year"] for r in records})
    items = sorted({(r["item_code"],r["original_item"]) for r in records})
    coverage = {code:sorted({r["year"] for r in records if r["item_code"] == code}) for code,_ in items}
    series_keys = sorted({(r["item_code"],r["measurement"],r["unit"]) for r in records})
    series_gaps = [dict(item_code=code,measurement=measurement,unit=unit,
        missing_years=sorted(expected_years-{r["year"] for r in records if (r["item_code"],r["measurement"],r["unit"]) == (code,measurement,unit)}))
        for code,measurement,unit in series_keys]
    for row in records:
        row.update(ingested_at=manifest["retrieved_at"], source_local_file=manifest["local_file"],
                   source_dataset="Crops and livestock products (QCL)",
                   revision_status="latest retrieved vintage; historical revisions unknown")
    normalized.update(schema_version=1, status="available", country="Jamaica", frequency="annual",
        retrieved_at=manifest["retrieved_at"], source_manifest=manifest_path.name,
        access_method=manifest["auth_method"], records=records,
        validation=dict(status="passed", source_rows=len(rows), observations=len(records),
            duplicate_rows=len(rows)-len(records), rejected_rows=len(normalized["rejected"]),
            years=years, requested_years=sorted(expected_years), missing_requested_years=sorted(expected_years-set(years)),
            items=[dict(code=c,label=label) for c,label in items], item_year_coverage=coverage,
            series_gaps=[r for r in series_gaps if r["missing_years"]],
            counts_by_measurement_unit={f"{measurement} ({unit})":sum((r["measurement"],r["unit"]) == (measurement,unit) for r in records)
                for measurement,unit in sorted({(r["measurement"],r["unit"]) for r in records})},
            counts_by_measurement={m:sum(r["measurement"]==m for r in records) for m in sorted({r["measurement"] for r in records})},
            flags={flag:sum(r["flag"]==flag for r in records) for flag in sorted({r["flag"] for r in records})},
            checks=["Jamaica/domain/year filter", "element/unit consistency", "finite non-negative values",
                    "unique annual natural keys", "no quarterly interpolation", "no Ministry crop mapping"]),
        dataset_version=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest())
    output = directory / f"qcl-jamaica-{start}-{end}.json"
    atomic_json(output, normalized)
    return normalized
