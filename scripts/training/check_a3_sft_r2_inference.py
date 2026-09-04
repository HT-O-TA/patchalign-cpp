"""CPU-only fail-closed preflight for A3.4/SFT-R2 fixed inference."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.baseline.run_a3_baseline import (
    load_cases,
    prompt_sha256,
    render_model_input,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.a3_sft_r2_inference_common import (
    validate_config,
    verify_holdout_manifest,
    verify_training_artifact,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(),
        "R2 inference preflight requires a clean worktree",
    )
    require(args.config.is_file(), "R2 inference config missing")
    require(args.environment_lock.is_file(), "environment lock missing")
    require(not args.report.exists(), f"refusing to overwrite preflight report: {args.report}")
    require(not args.output_dir.exists(), f"R2 inference output already exists: {args.output_dir}")

    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    training = verify_training_artifact(config)
    holdout_manifest = verify_holdout_manifest(config)
    model_path = Path(config["model"]["local_path"])
    require(model_path.is_dir(), "base model directory missing")
    require(
        sha256_file(model_path / "config.json") == config["model"]["config_sha256"],
        "model config hash mismatch",
    )

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    evaluation = config["evaluation"]
    manifest, cases = load_cases(
        Path(evaluation["holdout_root"]),
        evaluation["allowed_path"],
        evaluation["holdout_manifest"],
    )
    task_counts = Counter(case["item"]["task_level"] for case in cases)
    require(len(cases) == sum(evaluation["required_task_levels"].values()), "holdout denominator mismatch")
    require(dict(task_counts) == evaluation["required_task_levels"], "holdout composition mismatch")
    require(manifest["task_level_counts"] == evaluation["required_task_levels"], "holdout manifest composition mismatch")
    token_counts = []
    for case in cases:
        rendered = render_model_input(tokenizer, case["prompt"], evaluation["input_mode"])
        count = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
        require(count <= evaluation["generation"]["max_input_tokens"], f"prompt too long: {case['item']['case_id']}")
        token_counts.append(count)

    prompt_records = [
        {
            "case_id": case["item"]["case_id"],
            "task_level": case["item"]["task_level"],
            "prompt_version": evaluation["prompt_version"],
            "prompt_sha256": prompt_sha256(case["prompt"]),
            "prompt_text": case["prompt"],
            "public_test_id": case["public_test_id"],
            "rendered_input_tokens": token_count,
        }
        for case, token_count in zip(cases, token_counts, strict=True)
    ]
    prompts_text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in prompt_records
    )
    import hashlib

    prompts_sha256 = "sha256:" + hashlib.sha256(prompts_text.encode("utf-8")).hexdigest()
    require(
        prompts_sha256 == evaluation["prompt_artifact_sha256"],
        "formal prompt artifact hash mismatch",
    )

    report = {
        "version": "a3-sft-r2-inference-preflight-v1",
        "status": "passed",
        "checked_at": utc_now(),
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "environment_sha256": sha256_file(args.environment_lock),
        "model_config_sha256": config["model"]["config_sha256"],
        "source_training": {
            "git_commit": training["manifest"]["git_commit"],
            "manifest_sha256": config["source_training"]["manifest_sha256"],
            "adapter_sha256": config["source_training"]["adapter_sha256"],
            "checkpoint": config["source_training"]["checkpoint"],
        },
        "holdout": {
            "manifest_sha256": sha256_file(holdout_manifest),
            "cases": len(cases),
            "task_level_counts": dict(task_counts),
            "min_input_tokens": min(token_counts),
            "max_input_tokens": max(token_counts),
            "prompt_artifact_sha256": prompts_sha256,
        },
        "generation": evaluation["generation"],
        "input_mode": evaluation["input_mode"],
        "scoring_protocol": evaluation["scoring_protocol"],
        "output_dir_absent": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
