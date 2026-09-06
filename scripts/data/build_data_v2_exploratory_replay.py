#!/usr/bin/env python3
"""Build the fail-closed Data-v2 exploratory increment + replay mixture."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from jsonschema import Draft202012Validator

from scripts.data.audit_data_v2_supply import audit, read_json, read_jsonl, sha256_file
from scripts.data.build_a3_formal_sft_data import payload_key_from_sample


VERSION = "data-v2-exploratory-replay-v0.1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def stable_rank(seed: int, level: str, sample_id: str) -> str:
    raw = json.dumps([seed, level, sample_id], separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_replay(
    records: list[dict[str, Any]],
    seed: int,
    quotas: dict[str, int],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for level, quota in quotas.items():
        pool = [sample for sample in records if sample["task_level"] == level]
        chosen = sorted(
            pool,
            key=lambda sample: stable_rank(seed, level, sample["sample_id"]),
        )[:quota]
        require(len(chosen) == quota, f"insufficient replay {level}")
        selected.extend(chosen)
    return selected


def validate_config(repo: Path, config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected exploratory data version")
    require(config.get("seed") == 20260906, "unexpected selection seed")
    decision = config["decision"]
    require(sha256_file(repo / decision["path"]) == decision["sha256"], "ADR-0011 hash changed")
    scope = config["scope"]
    require(scope["exploratory_only"] is True, "exploratory boundary removed")
    require(scope["satisfies_data_v2_1_capacity_contract"] is False, "capacity failure hidden")
    require(scope["a5_dpo_started"] is False, "A5 unexpectedly enabled")
    require(scope["evaluation_gold_consumed"] is False, "evaluation gold enabled")
    supply = config["supply_audit"]
    for key in ("config", "candidate_audit", "run_manifest"):
        path = repo / supply[f"{key}_path"]
        require(path.is_file(), f"missing supply audit input: {path}")
        require(sha256_file(path) == supply[f"{key}_sha256"], f"supply audit {key} changed")
    selection = config["selection"]
    require(selection["replay_train"]["task_level_counts"] == {"function": 416, "file_window": 104}, "replay quota changed")
    require(selection["replay_train"]["total"] == 520, "replay total changed")
    require(selection["combined_counts"] == {"train": 780, "validation": 131}, "combined count changed")
    require(selection["combined_task_level_counts"] == {"train": {"function": 416, "file_window": 364}, "validation": {"function": 74, "file_window": 57}}, "task-level mix changed")
    require(selection["maximum_samples_per_family_across_v1_plus_increment"] == 2, "family cap changed")
    require(config["output"]["overwrite_allowed"] is False, "overwrite enabled")


def reproduce_increment(repo: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    supply = config["supply_audit"]
    audit_config = read_json(repo / supply["config_path"])
    _, available, _ = audit(audit_config, include_samples=True)
    expected = read_jsonl(repo / supply["candidate_audit_path"])
    projected = [
        {key: value for key, value in row.items() if key != "_sample"}
        for row in available
    ]
    require(
        sorted(projected, key=lambda row: row["candidate_id"])
        == sorted(expected, key=lambda row: row["candidate_id"]),
        "reproduced candidates differ from frozen supply audit",
    )
    counts = Counter(row["split"] for row in available)
    require(dict(counts) == supply["expected_available_increment"], "increment counts changed")
    return available


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(repo, config)
    output = Path(args.output_dir or config["output"]["root"])
    require(not output.exists(), f"refusing to overwrite output: {output}")

    available = reproduce_increment(repo, config)
    increment_samples: dict[str, list[dict[str, Any]]] = {"train": [], "validation": []}
    increment_meta: dict[str, dict[str, Any]] = {}
    for row in available:
        sample = dict(row["_sample"])
        sample["sample_id"] = "dv2inc:" + row["stable_id"][:24]
        increment_samples[row["split"]].append(sample)
        increment_meta[sample["sample_id"]] = {
            "role": "safe_increment",
            "candidate_id": row["candidate_id"],
            "stable_id": row["stable_id"],
            "new_family": row["new_family"],
            "source_shard": row["source_shard"],
            "payload_hash": row["payload_hash"],
        }

    formal = config["frozen_formal"]
    formal_root = Path(formal["root"])
    formal_train_path = formal_root / "train.jsonl"
    formal_validation_path = formal_root / "validation.jsonl"
    formal_lock_path = formal_root / "formal-data-lock.json"
    require(sha256_file(formal_lock_path) == formal["formal_data_lock_sha256"], "formal data lock changed")
    require(sha256_file(formal_train_path) == formal["train"]["sha256"], "formal train changed")
    require(sha256_file(formal_validation_path) == formal["validation"]["sha256"], "formal validation changed")
    formal_train = read_jsonl(formal_train_path)
    formal_validation = read_jsonl(formal_validation_path)
    require(len(formal_train) == formal["train"]["count"], "formal train count changed")
    require(len(formal_validation) == formal["validation"]["count"], "formal validation count changed")

    quotas = config["selection"]["replay_train"]["task_level_counts"]
    replay = select_replay(formal_train, config["seed"], quotas)
    replay_meta: dict[str, dict[str, Any]] = {}
    for sample in replay:
        level = sample["task_level"]
        replay_meta[sample["sample_id"]] = {
            "role": "formal_train_replay",
            "source_sample_id": sample["sample_id"],
            "rank": stable_rank(config["seed"], level, sample["sample_id"]),
        }

    train = replay + increment_samples["train"]
    train.sort(key=lambda sample: stable_rank(config["seed"], "combined", sample["sample_id"]))
    validation = sorted(increment_samples["validation"], key=lambda sample: sample["sample_id"])
    records = {"train": train, "validation": validation}

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[dict[str, str]] = []
    for split, values in records.items():
        for sample in values:
            require(sample["split"] == split, f"split mismatch: {sample['sample_id']}")
            require(sample["hidden_test_command"] is None, f"hidden test present: {sample['sample_id']}")
            errors.extend(
                {"sample_id": sample["sample_id"], "message": error.message}
                for error in validator.iter_errors(sample)
            )
    require(not errors, f"schema validation failed: {len(errors)}")

    ids = {split: {row["sample_id"] for row in values} for split, values in records.items()}
    families = {split: {row["repo_family"] for row in values} for split, values in records.items()}
    payloads = {split: {payload_key_from_sample(row) for row in values} for split, values in records.items()}
    require(len(ids["train"]) == len(train), "duplicate train sample ID")
    require(len(ids["validation"]) == len(validation), "duplicate validation sample ID")
    require(len(payloads["train"]) == len(train), "duplicate train payload")
    require(len(payloads["validation"]) == len(validation), "duplicate validation payload")
    require(ids["train"].isdisjoint(ids["validation"]), "sample overlap")
    require(payloads["train"].isdisjoint(payloads["validation"]), "payload overlap")
    require(families["train"].isdisjoint(families["validation"]), "repo family overlap")

    expected = config["selection"]
    counts = {split: len(values) for split, values in records.items()}
    task_levels = {
        split: dict(sorted(Counter(row["task_level"] for row in values).items()))
        for split, values in records.items()
    }
    require(counts == expected["combined_counts"], "final counts changed")
    require(task_levels == expected["combined_task_level_counts"], "final task-level counts changed")

    output.mkdir(parents=True)
    for split, values in records.items():
        write_jsonl(output / f"{split}.jsonl", values)
    report = {
        "version": VERSION,
        "sample_count": sum(counts.values()),
        "valid_count": sum(counts.values()),
        "invalid_count": 0,
        "errors": [],
    }
    write_json(output / "schema-validation-report.json", report)
    data_files = {
        f"{split}.jsonl": sha256_file(output / f"{split}.jsonl")
        for split in ("train", "validation")
    }
    manifest = {
        "version": VERSION,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256_file(args.config),
        "counts": counts,
        "task_level_counts": task_levels,
        "source_counts": {
            split: dict(sorted(Counter(row["source_dataset"] for row in values).items()))
            for split, values in records.items()
        },
        "edit_type_counts": {
            split: dict(sorted(Counter(row["edit_type"] for row in values).items()))
            for split, values in records.items()
        },
        "roles": {
            "train": dict(sorted(Counter((increment_meta | replay_meta)[row["sample_id"]]["role"] for row in train).items())),
            "validation": {"safe_increment": len(validation)},
        },
        "selected": {**replay_meta, **increment_meta},
        "data_files": data_files,
        "isolation": {
            "sample_overlap": 0,
            "payload_overlap": 0,
            "repo_family_overlap": 0,
            "formal_holdout_content_read": False,
            "confirmation_content_read": False,
            "external_content_read": False,
            "evaluation_gold_consumed": False,
        },
        "interpretation": {
            "exploratory_only": True,
            "satisfies_data_v2_1_capacity_contract": False,
            "gpu_training_requires_separate_passed_preflight": True,
        },
    }
    write_json(output / "selection-manifest.json", manifest)
    names = ["train.jsonl", "validation.jsonl", "selection-manifest.json", "schema-validation-report.json"]
    (output / "sha256sums.txt").write_text(
        "".join(f"{sha256_file(output / name).removeprefix('sha256:')}  {name}\n" for name in names),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "counts": counts,
        "task_level_counts": task_levels,
        "source_counts": manifest["source_counts"],
        "data_files": data_files,
        "isolation": manifest["isolation"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
