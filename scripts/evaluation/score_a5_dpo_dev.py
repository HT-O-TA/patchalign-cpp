#!/usr/bin/env python3
"""Execute-score one A5 model over the frozen 64-case independent dev set."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from jsonschema import Draft202012Validator

from scripts.baseline.score_a3_baseline import A31_SCORING_PROTOCOL, score_prediction, summarize
from scripts.evaluation.a5_dpo_dev_common import ROLES, read_json, read_jsonl, resolve_adapter, validate_config, verify_dataset
from scripts.training.a3_formal_common import require, sha256_file, write_json


def selection_metrics(scores: list[dict]) -> dict[str, int]:
    return {
        "pass_count": sum(row["success"] for row in scores),
        "hidden_test_success": sum(row["stages"]["hidden"]["status"] == "passed" for row in scores),
        "public_test_success": sum(row["stages"]["public"]["status"] == "passed" for row in scores),
        "compile_success": sum(row["stages"]["build"]["status"] == "passed" for row in scores),
        "apply_success": sum(row["stages"]["apply"]["status"] == "passed" for row in scores),
        "timeouts": sum(any(stage.get("timed_out", False) or any(item.get("timed_out", False) for item in stage.get("outcomes", [])) for stage in row["stages"].values()) for row in scores),
        "regression_failures": sum(row["terminal_classification"] == "regression_failed" for row in scores),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 dev scoring requires a clean worktree")
    require(args.output_dir == Path(config["outputs"]["scoring_root"]) / args.role, "unexpected A5 dev scoring output")
    require(not args.output_dir.exists(), "refusing to overwrite A5 dev scoring")
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    root, manifest = verify_dataset(config)
    model_identity = resolve_adapter(config, args.role)
    inference_dir = Path(config["outputs"]["inference_root"]) / args.role
    inference_manifest = read_json(inference_dir / "run-manifest.json")
    predictions_path = inference_dir / "predictions.jsonl"
    require(inference_manifest["git_commit"] == commit, "A5 dev inference/scoring commit mismatch")
    require(inference_manifest["config_sha256"] == sha256_file(args.config), "A5 dev inference config mismatch")
    require(inference_manifest["adapter_sha256"] == model_identity["adapter_sha256"], "A5 dev inference adapter mismatch")
    require(inference_manifest["prediction_artifact_sha256"] == sha256_file(predictions_path), "A5 dev predictions changed")
    predictions = read_jsonl(predictions_path)
    require(len(predictions) == config["dataset"]["case_count"], "A5 dev prediction denominator changed")
    require([row["sample_id"] for row in predictions] == [row["case_id"] for row in manifest["cases"]], "A5 dev prediction order changed")
    scoring = config["scoring"]
    require(sha256_file(repo / scoring["config"]) == scoring["config_sha256"], "scoring protocol config changed")
    require(sha256_file(Path(scoring["bwrap"])) == scoring["bwrap_sha256"], "Bubblewrap changed")

    scores = []
    for index, (item, prediction) in enumerate(zip(manifest["cases"], predictions, strict=True)):
        result = score_prediction(
            item, root / "cases" / item["case_id"], prediction,
            Path(scoring["bwrap"]), scoring_protocol=A31_SCORING_PROTOCOL,
        )
        scores.append(result)
        print(json.dumps({"role": args.role, "index": index + 1, "total": len(predictions), "terminal": result["terminal_classification"]}, sort_keys=True), flush=True)
    args.output_dir.mkdir(parents=True)
    scores_path = args.output_dir / "scores.jsonl"
    scores_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in scores), encoding="utf-8", newline="\n")
    summary = summarize(scores)
    summary.update({
        "version": "a5-dpo-dev-score-v1",
        "role": args.role,
        "selection_metrics": selection_metrics(scores),
        "prediction_sha256": sha256_file(predictions_path),
        "scores_sha256": sha256_file(scores_path),
    })
    write_json(args.output_dir / "summary.json", summary)
    run_manifest = {
        "schema_version": "0.1.0",
        "run_id": f"a5_dev_score_{args.role}_s{config['seed']}",
        "stage": "evaluation",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": commit,
        "dirty_worktree": False,
        "config_sha256": sha256_file(args.config),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "model_config_sha256": config["model"]["config_sha256"],
        "adapter_sha256": model_identity["adapter_sha256"],
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "environment_sha256": config["environment"]["lock_sha256"],
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": sha256_file(predictions_path),
        "execution_artifact_sha256": sha256_file(scores_path),
        "notes": f"role={args.role}; protocol={A31_SCORING_PROTOCOL}; summary={sha256_file(args.output_dir / 'summary.json')}",
    }
    Draft202012Validator(json.loads((repo / "schemas/run-manifest-v0.1.schema.json").read_text(encoding="utf-8"))).validate(run_manifest)
    write_json(args.output_dir / "run-manifest.json", run_manifest)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
