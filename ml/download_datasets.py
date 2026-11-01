"""Download the three public phishing datasets used by ThreatLens.

Sources (all CC BY 4.0):

1. PhiUSIIL Phishing URL Dataset - UCI Machine Learning Repository, dataset 967.
2. Phishing Email Detection Dataset (2025) - Zenodo record 17314806, merged corpus.
3. SMS Phishing Dataset - Mendeley Data, DOI 10.17632/f45bkkt8pr.1.

The script is deliberately dumb and reproducible: it streams each file to
``ml/datasets/raw``, records the size and SHA-256 in a manifest, and extracts
archives. It never fabricates data and it never overwrites a completed download
unless ``--force`` is supplied.

Usage:
    .\\.venv\\Scripts\\python.exe ml\\download_datasets.py
    .\\.venv\\Scripts\\python.exe ml\\download_datasets.py --only phiusiil
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "datasets" / "raw"
MANIFEST = RAW / "manifest.json"
CHUNK = 1024 * 1024

SOURCES = {
    "phiusiil": {
        "name": "PhiUSIIL Phishing URL Dataset",
        "publisher": "UCI Machine Learning Repository (dataset 967)",
        "url": "https://archive.ics.uci.edu/static/public/967/phiusiil+phishing+url+dataset.zip",
        "filename": "phiusiil_phishing_url_dataset.zip",
        "archive": True,
        "extract_to": "phiusiil",
        "license": "CC BY 4.0",
        "homepage": "https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset",
    },
    "email": {
        "name": "Phishing Email Detection Dataset (2025), merged corpus",
        "publisher": "Zenodo record 17314806",
        "url": "https://zenodo.org/api/records/17314806/files/Merged_Dataset.csv/content",
        "filename": "phishing_email_merged.csv",
        "archive": False,
        "license": "CC BY 4.0",
        "homepage": "https://zenodo.org/records/17314806",
    },
    "sms": {
        "name": "SMS Phishing Dataset for Machine Learning and Pattern Recognition",
        "publisher": "Mendeley Data, DOI 10.17632/f45bkkt8pr.1",
        "url": (
            "https://data.mendeley.com/public-files/datasets/f45bkkt8pr/files/"
            "edb361de-918d-469f-9106-e84823830665/file_downloaded"
        ),
        "filename": "sms_phishing_dataset.zip",
        "archive": True,
        "extract_to": "sms",
        "license": "CC BY 4.0",
        "homepage": "https://data.mendeley.com/datasets/f45bkkt8pr/1",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(key: str, source: dict, force: bool) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    destination = RAW / source["filename"]
    if destination.exists() and not force:
        print(f"[{key}] already present: {destination} ({destination.stat().st_size:,} bytes)")
    else:
        print(f"[{key}] downloading {source['url']}")
        temporary = destination.with_suffix(destination.suffix + ".part")
        with requests.get(source["url"], stream=True, timeout=(15, 180)) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            written = 0
            with temporary.open("wb") as handle:
                for block in response.iter_content(CHUNK):
                    if not block:
                        continue
                    handle.write(block)
                    written += len(block)
                    if total:
                        percent = written / total * 100
                        print(
                            f"\r[{key}] {written / 1_000_000:8.1f} / {total / 1_000_000:8.1f} MB "
                            f"({percent:5.1f}%)",
                            end="",
                            flush=True,
                        )
                    else:
                        print(f"\r[{key}] {written / 1_000_000:8.1f} MB", end="", flush=True)
        print()
        temporary.replace(destination)

    digest = sha256_file(destination)
    record = {
        "name": source["name"],
        "publisher": source["publisher"],
        "homepage": source["homepage"],
        "url": source["url"],
        "license": source["license"],
        "filename": source["filename"],
        "bytes": destination.stat().st_size,
        "sha256": digest,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }

    if source.get("archive"):
        target = RAW / source["extract_to"]
        if target.exists() and force:
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        print(f"[{key}] extracting {destination.name} -> {target}")
        with zipfile.ZipFile(destination) as archive:
            for member in archive.infolist():
                name = member.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    raise RuntimeError(f"Unsafe archive member: {name}")
                archive.extract(member, target)
        extracted = sorted(
            str(path.relative_to(RAW)).replace("\\", "/")
            for path in target.rglob("*")
            if path.is_file()
        )
        record["extracted"] = extracted
        print(f"[{key}] extracted {len(extracted)} file(s)")
        for name in extracted:
            print(f"  - {name}")

    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        choices=sorted(SOURCES),
        action="append",
        help="Download only the named source(s). Default: all.",
    )
    parser.add_argument("--force", action="store_true", help="Re-download and re-extract.")
    args = parser.parse_args()

    selected = args.only or list(SOURCES)
    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    for key in selected:
        try:
            manifest[key] = download(key, SOURCES[key], args.force)
        except Exception as exc:  # noqa: BLE001 - report the actual download error
            print(f"[{key}] FAILED: {exc}", file=sys.stderr)
            return 1

    RAW.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nManifest written to {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
