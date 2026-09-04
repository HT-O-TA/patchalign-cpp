"""CPU-only fail-closed preflight for A3.3 formal SFT and evaluation."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

from jsonschema import Draft202012Validator
from transformers import AutoTokenizer

from scripts.baseline.run_a3_baseline import load_cases, render_model_input
from scripts.training.a3_formal_common import (
    require,
    sha256_file,
    validate_config,
    verify_lock,
    verify_records,
    write_json,
)
from scripts.training.train_a3_sft_pilot import encode_example


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
        "preflight requires a clean worktree",
    )
    lock = verify_lock(args.config, config)
    records = verify_records(config)

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for values in records.values():
        for record in values:
            validator.validate(record)

    model_path = Path(config["model"]["local_path"])
    require(model_path.is_dir(), "model directory missing")
    require(
        sha256_file(model_path / "config.json") == config["model"]["config_sha256"],
        "model config hash mismatch",
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    encoded = {
        split: [
            encode_example(tokenizer, sample, config["training"]["max_sequence_tokens"])
            for sample in values
        ]
        for split, values in records.items()
    }

    holdout_root = Path(config["evaluation"]["holdout_root"])
    manifest, cases = load_cases(holdout_root, config["evaluation"]["allowed_path"])
    require(manifest["version"] == "a3-formal-holdout-v1", "wrong holdout version")
    require(
        manifest["task_level_counts"] == config["evaluation"]["required_task_levels"],
        "holdout composition mismatch",
    )
    require(len(cases) == 500, "holdout case denominator mismatch")
    public_counts = Counter(len(json.loads((case["case_dir"] / "test-partition.json").read_text())["public"]) for case in cases)
    require(all(key >= 1 for key in public_counts), "holdout case without public tests")
    holdout_prompt_tokens = [
        len(
            tokenizer(
                render_model_input(
                    tokenizer,
                    case["prompt"],
                    config["evaluation"]["input_mode"],
                ),
                add_special_tokens=True,
            )["input_ids"]
        )
        for case in cases
    ]
    require(
        max(holdout_prompt_tokens)
        <= config["evaluation"]["generation"]["max_input_tokens"],
        "holdout prompt exceeds max_input_tokens",
    )

    report = {
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "version": "a3-formal-preflight-v1",
        "status": "passed",
        "config_sha256": sha256_file(args.config),
        "environment_sha256": sha256_file(args.environment_lock),
        "data_lock_sha256": sha256_file(
            Path(config["data"]["root"]) / config["data"]["freeze_lock"]
        ),
        "data_lock_version": lock["version"],
        "counts": {split: len(values) for split, values in records.items()},
        "holdout_count": len(cases),
        "token_stats": {
            split: {
                "count": len(values),
                "min": min(item["sequence_tokens"] for item in values),
                "max": max(item["sequence_tokens"] for item in values),
                "total": sum(item["sequence_tokens"] for item in values),
            }
            for split, values in encoded.items()
        },
        "holdout_public_test_count_distribution": {
            str(key): value for key, value in sorted(public_counts.items())
        },
        "holdout_prompt_token_stats": {
            "count": len(holdout_prompt_tokens),
            "min": min(holdout_prompt_tokens),
            "max": max(holdout_prompt_tokens),
            "total": sum(holdout_prompt_tokens),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists(), f"refusing to overwrite preflight report: {args.output}")
    write_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
