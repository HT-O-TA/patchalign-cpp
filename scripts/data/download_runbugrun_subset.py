"""Download and verify the minimum RunBugRun payload for the A1 C++ pilot.

The upstream Manifest is the authority for asset names, checksums, and sizes.
This script deliberately fetches only the C++ train/validation bug shards plus
the shared tests and index required to replay them; it never guesses filenames.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = (
    "https://github.com/giganticode/run_bug_run_data/releases/download/v{version}/"
)
MANIFEST_NAME = "Manifest.json.gz"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "PatchAlign-Cpp-A1/1.0"})
    with urlopen(request, timeout=90) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def load_manifest(path: Path) -> dict[str, object]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("RunBugRun Manifest has no files list")
    return manifest


def is_required(entry: dict[str, object]) -> bool:
    kind = entry.get("type")
    if kind in {"tests", "index"}:
        return True
    return (
        kind == "bugs"
        and entry.get("language") == "cpp"
        and entry.get("split") in {"train", "valid", "validation"}
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    # The software repository has a separate ``v2`` tag.  The data repository's
    # current release is ``v0.0.1``; do not conflate these version namespaces.
    parser.add_argument("--version", default="0.0.1")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base_url = args.base_url.format(version=args.version)
    manifest_path = output / MANIFEST_NAME
    if not manifest_path.exists():
        fetch(base_url + MANIFEST_NAME, manifest_path)
    manifest = load_manifest(manifest_path)

    selected = [entry for entry in manifest["files"] if isinstance(entry, dict) and is_required(entry)]
    cpp_shards = [entry for entry in selected if entry.get("type") == "bugs"]
    if not cpp_shards:
        raise ValueError("Manifest contains no C++ train/validation bug shard")
    if not any(entry.get("type") == "tests" for entry in selected):
        raise ValueError("Manifest contains no shared tests payload")
    if not any(entry.get("type") == "index" for entry in selected):
        raise ValueError("Manifest contains no index payload")

    records: list[dict[str, object]] = []
    for entry in selected:
        filename = entry.get("filename")
        expected_md5 = entry.get("md5")
        if not isinstance(filename, str) or not filename or Path(filename).is_absolute() or ".." in Path(filename).parts:
            raise ValueError(f"unsafe or missing filename in Manifest: {filename!r}")
        destination = output / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            fetch(base_url + filename, destination)
        actual_md5 = md5(destination)
        if isinstance(expected_md5, str) and actual_md5 != expected_md5:
            raise ValueError(f"MD5 mismatch for {filename}: {actual_md5} != {expected_md5}")
        records.append(
            {
                "filename": filename,
                "type": entry.get("type"),
                "split": entry.get("split"),
                "language": entry.get("language"),
                "bytes": destination.stat().st_size,
                "expected_md5": expected_md5,
                "actual_md5": actual_md5,
                "sha256": "sha256:" + sha256(destination),
            }
        )

    source_record = {
        "source_dataset": "RunBugRun",
        "dataset_version": args.version,
        "base_url": base_url,
        "manifest": {
            "filename": MANIFEST_NAME,
            "sha256": "sha256:" + sha256(manifest_path),
        },
        "selection": "C++ bugs in train/valid plus shared tests and index",
        "files": sorted(records, key=lambda record: str(record["filename"])),
    }
    (output / "source-record.json").write_text(
        json.dumps(source_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(source_record, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
