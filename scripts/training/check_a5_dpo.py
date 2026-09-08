#!/usr/bin/env python3
"""CPU-only fail-closed preflight for the frozen A5 DPO experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import subprocess
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.a5_dpo_common import (
    EXPECTED_PACKAGES,
    dpo_rows,
    read_json,
    validate_config,
    verify_frozen_inputs,
)


VERSION = "a5-dpo-cpu-preflight-v1.1"


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def summarize(values: list[int]) -> dict[str, float | int]:
    return {
        "min": min(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "refusing to overwrite A5 DPO preflight")
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(config)
    pairs = verify_frozen_inputs(config, repo)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "DPO preflight requires a clean worktree")

    installed = {name: importlib.metadata.version(name) for name in EXPECTED_PACKAGES}
    require(installed == EXPECTED_PACKAGES, "DPO package versions changed")
    from transformers import AutoTokenizer
    from trl import DPOTrainer

    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["local_path"], local_files_only=True,
        trust_remote_code=False, use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    limits = config["training"]
    prompt_lengths: list[int] = []
    chosen_lengths: list[int] = []
    rejected_lengths: list[int] = []
    total_lengths: list[int] = []
    longest_index = 0
    rows = dpo_rows(pairs)
    for index, row in enumerate(rows):
        encoded = DPOTrainer.tokenize_row(
            row, tokenizer, max_prompt_length=None,
            max_completion_length=None, add_special_tokens=False,
            is_chat=False,
        )
        prompt = len(encoded["prompt_input_ids"])
        chosen = len(encoded["chosen_input_ids"])
        rejected = len(encoded["rejected_input_ids"])
        total = prompt + max(chosen, rejected)
        prompt_lengths.append(prompt)
        chosen_lengths.append(chosen)
        rejected_lengths.append(rejected)
        total_lengths.append(total)
        if total > total_lengths[longest_index]:
            longest_index = index
    require(max(prompt_lengths) <= limits["max_prompt_tokens"], "DPO prompt would be truncated")
    require(max(chosen_lengths + rejected_lengths) <= limits["max_completion_tokens"], "DPO completion would be truncated")
    require(max(total_lengths) <= limits["max_sequence_tokens"], "DPO sequence would be truncated")

    report: dict[str, Any] = {
        "version": VERSION,
        "status": "passed",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "environment_sha256": config["environment"]["lock_sha256"],
        "preferences_sha256": config["data"]["preferences_sha256"],
        "dev_exec_manifest_sha256": config["data"]["dev_exec_manifest_sha256"],
        "pair_count": len(rows),
        "chosen_success_pairs": config["data"]["expected_chosen_success_pairs"],
        "packages": installed,
        "token_limits": {
            "prompt": limits["max_prompt_tokens"],
            "completion": limits["max_completion_tokens"],
            "sequence": limits["max_sequence_tokens"],
        },
        "token_lengths": {
            "prompt": summarize(prompt_lengths),
            "chosen": summarize(chosen_lengths),
            "rejected": summarize(rejected_lengths),
            "sequence": summarize(total_lengths),
        },
        "truncated_rows": 0,
        "longest_pair_id": pairs[longest_index]["pair_id"],
        "expected_optimizer_steps_per_variant": limits["expected_optimizer_steps"],
        "variants": config["variants"],
        "cuda_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
