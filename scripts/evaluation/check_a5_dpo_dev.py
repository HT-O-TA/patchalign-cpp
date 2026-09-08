#!/usr/bin/env python3
"""CPU-only preflight freezing prompts and model identities for A5 DPO dev evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.baseline.run_a3_baseline import load_cases, prompt_sha256, render_model_input
from scripts.evaluation.a5_dpo_dev_common import ROLES, resolve_adapter, read_json, validate_config, verify_dataset
from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "a5-dpo-dev-preflight-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 dev preflight requires a clean worktree")
    output = Path(config["outputs"]["preflight"])
    prompts_path = Path(config["outputs"]["prompts"])
    require(not output.exists() and not prompts_path.exists(), "refusing to overwrite A5 dev preflight")
    root, manifest = verify_dataset(config)

    require(sha256_file(Path(config["model"]["local_path"]) / "config.json") == config["model"]["config_sha256"], "base model config changed")
    scoring = config["scoring"]
    require(sha256_file(repo / scoring["config"]) == scoring["config_sha256"], "scoring config changed")
    require(sha256_file(Path(scoring["bwrap"])) == scoring["bwrap_sha256"], "Bubblewrap changed")
    require(sha256_file(Path(config["environment"]["lock"])) == config["environment"]["lock_sha256"], "environment lock changed")
    models = {role: resolve_adapter(config, role) for role in ROLES}

    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["local_path"], local_files_only=True,
        trust_remote_code=False, use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    _, cases = load_cases(root, config["inference"]["allowed_path"], config["dataset"]["manifest"])
    require(len(cases) == config["dataset"]["case_count"], "A5 dev case denominator changed")
    prompt_rows = []
    for case in cases:
        rendered = render_model_input(tokenizer, case["prompt"], config["inference"]["input_mode"])
        tokens = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
        require(tokens <= config["inference"]["max_input_tokens"], f"A5 dev prompt too long: {case['item']['case_id']}")
        prompt_rows.append({
            "case_id": case["item"]["case_id"],
            "problem_id": str(case["item"]["problem_id"]),
            "task_level": case["item"]["task_level"],
            "prompt_version": config["inference"]["prompt_version"],
            "prompt_sha256": prompt_sha256(case["prompt"]),
            "prompt_text": case["prompt"],
            "public_test_id": case["public_test_id"],
            "input_tokens": tokens,
        })
    require(len({row["case_id"] for row in prompt_rows}) == len(prompt_rows), "duplicate A5 dev case")
    require(len({row["problem_id"] for row in prompt_rows}) == len(prompt_rows), "duplicate A5 dev family")
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in prompt_rows)
    prompts_path.parent.mkdir(parents=True, exist_ok=True)
    prompts_path.write_text(payload, encoding="utf-8", newline="\n")
    report = {
        "version": VERSION,
        "status": "passed",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "environment_sha256": config["environment"]["lock_sha256"],
        "models": models,
        "case_count": len(prompt_rows),
        "case_order_sha256": "sha256:" + hashlib.sha256("\n".join(row["case_id"] for row in prompt_rows).encode()).hexdigest(),
        "prompts_sha256": sha256_file(prompts_path),
        "prompt_tokens": {
            "min": min(row["input_tokens"] for row in prompt_rows),
            "max": max(row["input_tokens"] for row in prompt_rows),
            "mean": sum(row["input_tokens"] for row in prompt_rows) / len(prompt_rows),
        },
        "a4_training_overlap": manifest["a4_selected_overlap"],
        "cuda_used": False,
    }
    write_json(output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
