"""CPU-only fail-closed preflight for A3.4/SFT-R2."""

from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
import subprocess

from jsonschema import Draft202012Validator

from patchalign.evaluation.patches import enforce_patch_policy, parse_unified_diff
from scripts.baseline.run_a3_baseline import load_cases, render_model_input
from scripts.training.a3_formal_common import load_jsonl, require, sha256_file, write_json
from scripts.training.a3_sft_r2_common import (
    validate_config,
    verify_data,
    verify_initial_adapter,
)
from scripts.training.train_a3_sft_pilot import (
    build_training_prompt,
    encode_example,
    normalized_target,
)


def token_stats(values: list[dict[str, object]]) -> dict[str, int]:
    lengths = [int(value["sequence_tokens"]) for value in values]
    return {
        "count": len(lengths),
        "min": min(lengths),
        "max": max(lengths),
        "total": sum(lengths),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    require(args.environment_lock.is_file(), "environment lock missing")
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(),
        "R2 preflight requires a clean worktree",
    )
    records, selection_manifest = verify_data(repo, args.config, config)
    adapter, source_manifest = verify_initial_adapter(config)

    model_path = Path(config["model"]["local_path"])
    require(model_path.is_dir(), "model directory missing")
    require(
        sha256_file(model_path / "config.json") == config["model"]["config_sha256"],
        "model config hash mismatch",
    )
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    max_tokens = config["training"]["max_sequence_tokens"]
    encoded = {
        split: [encode_example(tokenizer, record, max_tokens) for record in values]
        for split, values in records.items()
    }

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for values in records.values():
        for record in values:
            validator.validate(record)
            parsed = parse_unified_diff(normalized_target(record))
            enforce_patch_policy(parsed, record["allowed_paths"])
            prompt = build_training_prompt(record)
            require(prompt.endswith("Unified diff:\n"), "R2 training prompt suffix changed")
            require(record["gold_patch"] not in prompt, "R2 gold patch leaked into prompt")

    reference_path = Path(config["data"]["reference_validation_root"]) / "validation.jsonl"
    require(reference_path.is_file(), "reference validation missing")
    require(
        sha256_file(reference_path) == config["data"]["reference_validation_sha256"],
        "reference validation hash mismatch",
    )
    reference_records = load_jsonl(reference_path)
    require(
        len(reference_records) == config["data"]["reference_validation_count"],
        "reference validation count mismatch",
    )
    reference_encoded = [encode_example(tokenizer, record, max_tokens) for record in reference_records]

    evaluation = config["evaluation"]
    holdout_root = Path(evaluation["holdout_root"])
    holdout_manifest_path = holdout_root / "a2-manifest.json"
    require(holdout_manifest_path.is_file(), "formal holdout manifest missing")
    require(
        sha256_file(holdout_manifest_path) == evaluation["holdout_manifest_sha256"],
        "formal holdout manifest hash mismatch",
    )
    holdout_manifest, cases = load_cases(holdout_root, evaluation["allowed_path"])
    require(holdout_manifest["version"] == "a3-formal-holdout-v1", "wrong holdout version")
    require(holdout_manifest["task_level_counts"] == evaluation["required_task_levels"], "holdout composition mismatch")
    require(len(cases) == config["comparison"]["fixed_denominator"], "holdout denominator mismatch")
    holdout_tokens = [
        len(
            tokenizer(
                render_model_input(tokenizer, case["prompt"], evaluation["input_mode"]),
                add_special_tokens=True,
            )["input_ids"]
        )
        for case in cases
    ]
    require(
        max(holdout_tokens) <= evaluation["generation"]["max_input_tokens"],
        "holdout prompt exceeds max input tokens",
    )

    report = {
        "version": "a3-sft-r2-preflight-v1",
        "status": "passed",
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "config_sha256": sha256_file(args.config),
        "environment_sha256": sha256_file(args.environment_lock),
        "selection_manifest_sha256": config["data"]["selection_manifest_sha256"],
        "selection_counts": selection_manifest["counts"],
        "selection_tag_counts": selection_manifest["tag_counts"],
        "source_adapter": {
            "path": str(adapter),
            "sha256": config["initialization"]["adapter_sha256"],
            "source_run_id": source_manifest["run_id"],
        },
        "token_stats": {
            "train": token_stats(encoded["train"]),
            "validation": token_stats(encoded["validation"]),
            "reference_validation": token_stats(reference_encoded),
            "holdout": {
                "count": len(holdout_tokens),
                "min": min(holdout_tokens),
                "max": max(holdout_tokens),
                "total": sum(holdout_tokens),
            },
        },
        "composition": {
            split: {
                "sources": dict(sorted(Counter(record["source_dataset"] for record in values).items())),
                "task_levels": dict(sorted(Counter(record["task_level"] for record in values).items())),
            }
            for split, values in records.items()
        },
        "optimizer_steps": 150,
        "holdout_count": len(cases),
        "holdout_task_levels": holdout_manifest["task_level_counts"],
        "inference_semantics_unchanged": True,
    }
    require(not args.output.exists(), f"refusing to overwrite preflight report: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
