"""CPU-only fail-closed preflight for the frozen A3.2 SFT pilot."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from patchalign.evaluation.patches import enforce_patch_policy, parse_unified_diff
from scripts.baseline.run_a3_baseline import load_cases, prompt_sha256, render_model_input
from scripts.training.train_a3_sft_pilot import (
    build_training_prompt,
    encode_example,
    load_jsonl,
    normalized_target,
    require,
    sha256_file,
    validate_config,
)


def validate_split(
    records: list[dict[str, Any]],
    split: str,
    config: dict[str, Any],
    validator: Draft202012Validator,
) -> dict[str, Any]:
    require(
        len(records) == config["data"]["expected_counts"][split],
        f"{split} count mismatch",
    )
    seen = set()
    for record in records:
        validator.validate(record)
        require(record["split"] == split, f"wrong split: {record['sample_id']}")
        require(record["sample_id"] not in seen, f"duplicate sample: {record['sample_id']}")
        seen.add(record["sample_id"])
        require(len(record["allowed_paths"]) == 1, "pilot requires one allowed path")
        parsed = parse_unified_diff(normalized_target(record))
        enforce_patch_policy(parsed, record["allowed_paths"])
        prompt = build_training_prompt(record)
        require(prompt.endswith("Unified diff:\n"), "training prompt suffix changed")
        require(record["gold_patch"] not in prompt, "gold patch leaked into prompt")
    task_levels = Counter(record["task_level"] for record in records)
    require(
        dict(task_levels) == config["data"]["expected_task_levels"][split],
        f"{split} task-level composition mismatch",
    )
    return {
        "count": len(records),
        "task_levels": dict(sorted(task_levels.items())),
        "edit_types": dict(sorted(Counter(x["edit_type"] for x in records).items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--m0-inference-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    data_root = Path(config["data"]["root"])
    paths = {
        "manifest": data_root / config["data"]["manifest"],
        "train": data_root / config["data"]["train"],
        "validation": data_root / config["data"]["validation"],
    }
    for name, path in paths.items():
        require(path.is_file(), f"missing {name}: {path}")
        require(
            sha256_file(path) == config["data"][f"{name}_sha256"],
            f"{name} hash mismatch",
        )

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text())
    validator = Draft202012Validator(schema)
    records = {name: load_jsonl(paths[name]) for name in ("train", "validation")}
    report = {
        name: validate_split(items, name, config, validator)
        for name, items in records.items()
    }
    train_families = {record["repo_family"] for record in records["train"]}
    validation_families = {record["repo_family"] for record in records["validation"]}
    require(
        train_families.isdisjoint(validation_families),
        "train/validation repository families overlap",
    )

    from transformers import AutoTokenizer

    model_path = Path(config["model"]["local_path"])
    require(model_path.is_dir(), "model directory is missing")
    require(
        sha256_file(model_path / "config.json") == config["model"]["config_sha256"],
        "model config hash mismatch",
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    max_tokens = config["training"]["max_sequence_tokens"]
    tokenized = {
        split: [encode_example(tokenizer, sample, max_tokens) for sample in items]
        for split, items in records.items()
    }
    report["token_stats"] = {
        split: {
            "min": min(item["sequence_tokens"] for item in items),
            "max": max(item["sequence_tokens"] for item in items),
            "total": sum(item["sequence_tokens"] for item in items),
        }
        for split, items in tokenized.items()
    }
    report["truncated_examples"] = 0

    evaluation = config["evaluation"]
    holdout = Path(evaluation["holdout_root"])
    require(
        sha256_file(holdout / "a2-manifest.json")
        == evaluation["holdout_manifest_sha256"],
        "A2 holdout hash mismatch",
    )
    manifest, cases = load_cases(holdout, evaluation["allowed_path"])
    require(
        manifest["task_level_counts"] == {"function": 50, "file_window": 20},
        "A2 holdout composition changed",
    )
    m0_predictions = [
        json.loads(line)
        for line in (args.m0_inference_dir / "predictions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    expected_identity = [
        (
            case["item"]["case_id"],
            evaluation["prompt_version"],
            prompt_sha256(case["prompt"]),
        )
        for case in cases
    ]
    actual_identity = [
        (record["sample_id"], record["prompt_version"], record["prompt_sha256"])
        for record in m0_predictions
    ]
    require(actual_identity == expected_identity, "A3.2/M0 evaluation prompt identity mismatch")
    evaluation_tokens = [
        len(
            tokenizer(
                render_model_input(tokenizer, case["prompt"], "raw_completion"),
                add_special_tokens=True,
            )["input_ids"]
        )
        for case in cases
    ]
    require(
        max(evaluation_tokens) <= evaluation["generation"]["max_input_tokens"],
        "evaluation prompt token limit exceeded",
    )
    report["evaluation"] = {
        "cases": len(cases),
        "task_levels": manifest["task_level_counts"],
        "prompt_tokens_min": min(evaluation_tokens),
        "prompt_tokens_max": max(evaluation_tokens),
        "same_m0_prompt_identity": True,
    }
    report["status"] = "passed"
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
