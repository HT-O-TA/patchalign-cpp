#!/usr/bin/env python3
"""CPU-only preflight for the selected DPO final evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.baseline.run_a3_baseline import load_cases, prompt_sha256, render_model_input
from scripts.evaluation.a5_dpo_final_common import (
    DATASETS,
    read_json,
    read_jsonl,
    validate_config,
    verify_baseline,
    verify_dataset,
    verify_selection_and_adapter,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 final preflight requires a clean worktree")
    output = Path(config["outputs"]["preflight"])
    require(not output.exists(), "refusing to overwrite A5 final preflight")
    require(not Path(config["outputs"]["comparison"]).exists(), "A5 final comparison already exists")
    require(not Path(config["outputs"]["failure_analysis"]).exists(), "A5 final failure analysis already exists")
    require(sha256_file(Path(config["model"]["local_path"]) / "config.json") == config["model"]["config_sha256"], "base model config changed")
    require(sha256_file(repo / config["scoring"]["config"]) == config["scoring"]["config_sha256"], "scoring config changed")
    require(sha256_file(Path(config["scoring"]["bwrap"])) == config["scoring"]["bwrap_sha256"], "Bubblewrap changed")
    require(sha256_file(repo / config["quality_gates"]["path"]) == config["quality_gates"]["sha256"], "quality gates changed")
    require(sha256_file(Path(config["environment"]["lock"])) == config["environment"]["lock_sha256"], "environment changed")
    selection = verify_selection_and_adapter(config)

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(config["model"]["local_path"], local_files_only=True, trust_remote_code=False, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    datasets = {}
    for name in DATASETS:
        dataset = config["datasets"][name]
        root, manifest = verify_dataset(config, name)
        verify_baseline(config, name)
        require(not (Path(config["outputs"]["root"]) / name / "inference" / "run-manifest.json").exists(), f"{name} inference already complete")
        require(not (Path(config["outputs"]["root"]) / name / "scoring").exists(), f"{name} scoring already exists")
        if dataset["kind"] == "cpp":
            _, cases = load_cases(root, dataset["allowed_path"], dataset["manifest"])
            rows = []
            counts = []
            for case in cases:
                rendered = render_model_input(tokenizer, case["prompt"], dataset["input_mode"])
                count = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
                require(count <= config["generation"]["max_input_tokens"], f"prompt too long: {case['item']['case_id']}")
                counts.append(count)
                rows.append({
                    "case_id": case["item"]["case_id"],
                    "task_level": case["item"]["task_level"],
                    "prompt_version": dataset["prompt_version"],
                    "prompt_sha256": prompt_sha256(case["prompt"]),
                    "prompt_text": case["prompt"],
                    "public_test_id": case["public_test_id"],
                    "rendered_input_tokens": count,
                })
            prompt_bytes = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")
            import hashlib
            prompt_hash = "sha256:" + hashlib.sha256(prompt_bytes).hexdigest()
            require(prompt_hash == dataset["prompt_artifact_sha256"], f"{name} prompt artifact changed")
        else:
            prompts = read_jsonl(root / dataset["prompts"])
            require(len(prompts) == dataset["case_count"], "Defects4C prompt denominator changed")
            counts = []
            for prompt in prompts:
                count = len(tokenizer(prompt["prompt_text"], add_special_tokens=True)["input_ids"])
                require(count == prompt["input_tokens"], f"Defects4C token count changed: {prompt['case_id']}")
                require(count <= config["generation"]["max_input_tokens"], f"Defects4C prompt too long: {prompt['case_id']}")
                counts.append(count)
            prompt_hash = dataset["prompt_artifact_sha256"]
        datasets[name] = {
            "manifest_sha256": dataset["manifest_sha256"],
            "prompt_artifact_sha256": prompt_hash,
            "case_count": len(manifest["cases"]),
            "input_tokens": {"min": min(counts), "max": max(counts), "mean": sum(counts) / len(counts)},
            "baseline_adapter_sha256": dataset["baseline"]["adapter_sha256"],
        }
    report = {
        "version": "a5-dpo-final-preflight-v1",
        "status": "passed",
        "created_at": utc_now(),
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "selection_sha256": config["selection"]["sha256"],
        "selected": selection["selected"],
        "adapter_sha256": config["adapter"]["sha256"],
        "environment_sha256": config["environment"]["lock_sha256"],
        "datasets": datasets,
        "cuda_used": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
