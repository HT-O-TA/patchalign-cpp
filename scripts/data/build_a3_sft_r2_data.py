"""Build the A3.4/SFT-R2 safety-focused subset from frozen A3.3 SFT data."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any


VERSION = "a3-sft-r2-data-v1"
SOURCE_VERSION = "a3-formal-data-lock-v1"
SOURCE_LOCK_SHA256 = "f37eef03ce0a96ad1fa14622b8b7ef6f30c3f6bcc8dad85addbb1e4c53d12a12"
SOURCE_FILE_SHA256 = {
    "train.jsonl": "c1cd80868632b845fa80a249ef8083ad2f5cf709e54dad63bcfe492a3ee3b400",
    "validation.jsonl": "6ee5cbed97c487ad5a0561b5f4b5179665137f6537dc411b81af91cbf5d13980",
}

LOOP_HEADER = re.compile(r"\b(?:for|while)\s*\(|\bdo\s*\{")
CONTROL_UPDATE = re.compile(
    r"(?:\+\+|--|\+=|-=|\*=|/=|%=|<<=|>>=|(?<![<>])(?:<=|>=|==|!=|<|>)(?![<>]))"
)
INDEX_OR_BOUND = re.compile(
    r"(?:\[[^\]\n]+\]|\.at\s*\(|\.size\s*\(|\.length\s*\(|"
    r"\b(?:size|length|count|limit|bound|begin|end|max|min|capacity)\w*\b)",
    re.IGNORECASE,
)
SCALE_OR_ALLOCATION = re.compile(
    r"(?:\b(?:resize|reserve|assign|malloc|calloc|realloc)\s*\(|"
    r"\bnew\s+[A-Za-z_:]|\b(?:rows?|cols?|width|height|capacity)\w*\b)",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def diff_code(patch: str) -> tuple[str, str]:
    changed: list[str] = []
    hunk: list[str] = []
    for line in patch.splitlines():
        if line.startswith(("--- ", "+++ ", "@@")):
            continue
        if line.startswith(("+", "-")):
            changed.append(line[1:])
            hunk.append(line[1:])
        elif line.startswith(" "):
            hunk.append(line[1:])
    return "\n".join(changed), "\n".join(hunk)


def safety_tags(sample: dict[str, Any]) -> list[str]:
    changed, hunk = diff_code(sample["gold_patch"])
    tags: list[str] = []
    changed_loop = bool(LOOP_HEADER.search(changed))
    nearby_loop = bool(LOOP_HEADER.search(hunk))
    changed_update = bool(CONTROL_UPDATE.search(changed))
    changed_bound = bool(INDEX_OR_BOUND.search(changed))
    if changed_loop or (nearby_loop and changed_update):
        tags.append("loop_control_or_progress")
    if changed_bound and changed_update:
        tags.append("boundary_or_index_update")
    if SCALE_OR_ALLOCATION.search(changed):
        tags.append("scale_or_allocation_complexity")
    return tags


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config_path = repo / "configs/data/a3_sft_r2_v1.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("version") != VERSION:
        raise RuntimeError("wrong R2 data config version")
    if config["selection"]["policy"] != "static-gold-diff-safety-v1":
        raise RuntimeError("wrong R2 selection policy")
    if config["selection"]["source_dataset"] != "RunBugRun":
        raise RuntimeError("wrong R2 source scope")
    if config["selection"]["task_level"] != "function":
        raise RuntimeError("wrong R2 task scope")
    if args.output_dir.exists():
        raise RuntimeError(f"refusing to overwrite output: {args.output_dir}")

    lock_path = args.source_root / "formal-data-lock.json"
    if not lock_path.is_file():
        raise RuntimeError("source data lock missing")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("version") != SOURCE_VERSION:
        raise RuntimeError("unexpected source data lock version")
    if sha256_file(lock_path) != SOURCE_LOCK_SHA256:
        raise RuntimeError("source data lock hash mismatch")

    selected: dict[str, list[dict[str, Any]]] = {}
    tags_by_id: dict[str, list[str]] = {}
    source_counts: dict[str, int] = {}
    for split in ("train", "validation"):
        name = f"{split}.jsonl"
        source_path = args.source_root / name
        if sha256_file(source_path) != SOURCE_FILE_SHA256[name]:
            raise RuntimeError(f"source file hash mismatch: {name}")
        records = load_jsonl(source_path)
        source_counts[split] = len(records)
        selected[split] = []
        for sample in records:
            if sample.get("split") != split:
                raise RuntimeError(f"split mismatch: {sample.get('sample_id')}")
            if sample.get("hidden_test_command") is not None:
                raise RuntimeError(f"hidden test content present: {sample['sample_id']}")
            if not (
                sample.get("source_dataset") == "RunBugRun"
                and sample.get("task_level") == "function"
            ):
                continue
            tags = safety_tags(sample)
            if tags:
                selected[split].append(sample)
                tags_by_id[sample["sample_id"]] = tags

    train_ids = {sample["sample_id"] for sample in selected["train"]}
    validation_ids = {sample["sample_id"] for sample in selected["validation"]}
    if train_ids & validation_ids:
        raise RuntimeError("train/validation sample overlap")
    if not selected["train"] or not selected["validation"]:
        raise RuntimeError("empty safety-focused split")

    args.output_dir.mkdir(parents=True)
    for split in ("train", "validation"):
        write_jsonl(args.output_dir / f"{split}.jsonl", selected[split])
    tag_counts = {
        split: dict(
            sorted(
                Counter(
                    tag
                    for sample in selected[split]
                    for tag in tags_by_id[sample["sample_id"]]
                ).items()
            )
        )
        for split in ("train", "validation")
    }
    manifest = {
        "version": VERSION,
        "selection_policy": "static-gold-diff-safety-v1",
        "source": {
            "version": SOURCE_VERSION,
            "formal_data_lock_sha256": f"sha256:{SOURCE_LOCK_SHA256}",
            "file_sha256": {
                name: f"sha256:{digest}" for name, digest in SOURCE_FILE_SHA256.items()
            },
            "counts": source_counts,
        },
        "counts": {split: len(values) for split, values in selected.items()},
        "tag_counts": tag_counts,
        "selected_sample_tags": {
            sample_id: tags_by_id[sample_id] for sample_id in sorted(tags_by_id)
        },
        "isolation": {
            "source_is_frozen_a3_sft_only": True,
            "source_and_task_scope": "RunBugRun/function",
            "formal_holdout_content_read": False,
            "hidden_test_content_read": False,
            "train_validation_sample_overlap": 0,
        },
        "data_files": {
            f"{split}.jsonl": f"sha256:{sha256_file(args.output_dir / f'{split}.jsonl')}"
            for split in ("train", "validation")
        },
    }
    expected = config["output"]
    if manifest["counts"] != expected["counts"]:
        raise RuntimeError("R2 output count mismatch")
    if manifest["tag_counts"] != expected["tag_counts"]:
        raise RuntimeError("R2 tag count mismatch")
    if manifest["data_files"] != expected["file_sha256"]:
        raise RuntimeError("R2 output hash mismatch")
    if config["source"]["formal_data_lock_sha256"] != f"sha256:{SOURCE_LOCK_SHA256}":
        raise RuntimeError("R2 source lock config mismatch")
    if config["source"]["file_sha256"] != {
        name: f"sha256:{digest}" for name, digest in SOURCE_FILE_SHA256.items()
    }:
        raise RuntimeError("R2 source file config mismatch")
    manifest["config_sha256"] = f"sha256:{sha256_file(config_path)}"
    write_json(args.output_dir / "selection-manifest.json", manifest)
    print(json.dumps({
        "version": manifest["version"],
        "selection_policy": manifest["selection_policy"],
        "counts": manifest["counts"],
        "tag_counts": manifest["tag_counts"],
        "data_files": manifest["data_files"],
        "isolation": manifest["isolation"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
