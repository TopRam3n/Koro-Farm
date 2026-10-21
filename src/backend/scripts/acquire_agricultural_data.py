"""Cache the Ministry's linked original PDFs, without guessing download paths.

Run from repository root: python -m src.backend.scripts.acquire_agricultural_data
Existing content-addressed files are reused; --refresh checks for new versions.
"""
import argparse
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/agriculture"
INDEXES = {
    "production": "all-island-estimates-crop-production-quarter",
    "price": "all-island-estimates-farmgate-prices-quarter",
    "area": "all-island-estimates-crop-area-reaped-quarter",
    "combined": "area-reaped-production-and-farmgate-prices",
}


def acquire(refresh=False):
    DATA.mkdir(parents=True, exist_ok=True)
    raw = DATA / "raw"
    raw.mkdir(exist_ok=True)
    manifest_path = DATA / "sources.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    known = {m["url"]: m for m in manifest}
    failures = []
    for kind, slug in INDEXES.items():
        index = "https://moa.gov.jm/agridata/" + slug
        try:
            html = urllib.request.urlopen(index, timeout=45).read()
            (raw / (kind + "-index.html")).write_bytes(html)
            links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html.decode(), re.S)
            for href, label in links:
                label = re.sub(r"<[^>]+>", "", unescape(label)).strip()
                year = re.search(r"\b(20\d{2})\b", label)
                if not year or not 2016 <= int(year[1]) <= 2026 or ".pdf" not in href.lower():
                    continue
                if "charter" in label.lower():
                    continue
                url = urljoin(index, unescape(href))
                if urlparse(url).hostname not in {"moa.gov.jm", "www.moa.gov.jm"}:
                    continue
                if url in known and not refresh and (ROOT / known[url]["local_path"]).exists():
                    continue
                try:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        content = response.read()
                        modified = response.headers.get("Last-Modified")
                    if not content.startswith(b"%PDF"):
                        raise ValueError("Response is not a PDF")
                    digest = hashlib.sha256(content).hexdigest()
                    path = raw / f"{kind}-{year[1]}-{digest[:12]}.pdf"
                    path.write_bytes(content)
                    entry = dict(url=url, index_url=index, label=label, kind=kind,
                                 year=int(year[1]), sha256=digest, local_path=path.relative_to(ROOT).as_posix(),
                                 retrieved_at=datetime.now(timezone.utc).isoformat(),
                                 http_last_modified=modified, publication_date=None,
                                 publication_note="HTTP Last-Modified is not a verified publication date.")
                    if not any(m["url"] == url and m["sha256"] == digest for m in manifest):
                        manifest.append(entry)
                    print(kind, year[1], len(content), path.name, flush=True)
                except Exception as exc:
                    failures.append(dict(url=url, error=str(exc)))
        except Exception as exc:
            failures.append(dict(url=index, error=str(exc)))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (DATA / "acquisition-errors.json").write_text(json.dumps(failures, indent=2) + "\n")
    print(f"Cached {len(manifest)} source versions; {len(failures)} download errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--refresh", action="store_true")
    acquire(parser.parse_args().refresh)
