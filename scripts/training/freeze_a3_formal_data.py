"""Validate and hash-lock the frozen A3.3 formal data products."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


LOCK_VERSION = "a3-formal-data-lock-v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    require(config["version"] == "a3-sft-formal-v1", "wrong formal config version")
    data_root = Path(config["data"]["root"])
    holdout_root = Path(config["evaluation"]["holdout_root"])
    lock_path = data_root / config["data"]["freeze_lock"]
    require(not lock_path.exists(), f"refusing to overwrite freeze lock: {lock_path}")

    data_files = [
        "dataset-manifest.json",
        "filter-report.json",
        "schema-validation-report.json",
        "split-report.json",
        "train.jsonl",
        "validation.jsonl",
        "sha256sums.txt",
    ]
    holdout_files = [
        "a2-manifest.json",
        "qualification-report.json",
        "qualification-results.jsonl",
        "sha256sums.txt",
    ]
    for name in data_files:
        require((data_root / name).is_file(), f"missing formal SFT file: {name}")
    for name in holdout_files:
        require((holdout_root / name).is_file(), f"missing formal holdout file: {name}")

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text())
    validator = Draft202012Validator(schema)
    records: dict[str, list[dict[str, Any]]] = {}
    for split in ("train", "validation"):
        records[split] = load_jsonl(data_root / f"{split}.jsonl")
        require(
            len(records[split]) == config["data"]["expected_counts"][split],
            f"{split} count mismatch",
        )
        for record in records[split]:
            validator.validate(record)
            require(record["split"] == split, f"wrong split: {record['sample_id']}")
        levels = Counter(record["task_level"] for record in records[split])
        sources = Counter(record["source_dataset"] for record in records[split])
        require(dict(levels) == config["data"]["expected_task_levels"][split], f"{split} task composition mismatch")
        require(dict(sources) == config["data"]["expected_sources"][split], f"{split} source composition mismatch")

    train_families = {record["repo_family"] for record in records["train"]}
    validation_families = {record["repo_family"] for record in records["validation"]}
    require(not train_families & validation_families, "train/validation family overlap")
    holdout = json.loads((holdout_root / "a2-manifest.json").read_text())
    require(holdout["version"] == "a3-formal-holdout-v1", "wrong holdout version")
    require(
        holdout["task_level_counts"] == config["evaluation"]["required_task_levels"],
        "holdout task composition mismatch",
    )
    require(len(holdout["cases"]) == 500, "formal holdout denominator mismatch")
    holdout_problems = {str(item["problem_id"]) for item in holdout["cases"]}
    require(len(holdout_problems) == 500, "holdout problem families are not unique")
    sft_problems = {
        record["repo_family"].rsplit(":", 1)[-1]
        for split in records.values()
        for record in split
        if record["source_dataset"] == "RunBugRun"
    }
    require(not sft_problems & holdout_problems, "SFT/formal holdout family overlap")

    lock = {
        "version": LOCK_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config_sha256": sha256_file(args.config),
        "data_root": str(data_root),
        "holdout_root": str(holdout_root),
        "data_files": {name: sha256_file(data_root / name) for name in data_files},
        "holdout_files": {name: sha256_file(holdout_root / name) for name in holdout_files},
        "counts": {split: len(value) for split, value in records.items()},
        "task_level_counts": {
            split: dict(Counter(item["task_level"] for item in value))
            for split, value in records.items()
        },
        "source_counts": {
            split: dict(Counter(item["source_dataset"] for item in value))
            for split, value in records.items()
        },
        "isolation": {
            "train_validation_family_overlap": 0,
            "sft_holdout_problem_overlap": 0,
        },
    }
    lock_path.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"lock": str(lock_path), "sha256": sha256_file(lock_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
