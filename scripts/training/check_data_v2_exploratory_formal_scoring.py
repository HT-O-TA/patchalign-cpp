"""Fail-closed preflight for Data-v2 exploratory formal scoring v2."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from jsonschema import Draft202012Validator

from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "data-v2-exploratory-formal-scoring-v0.1"
INFERENCE_COMMIT = "c1854abb12e1daee1adb7efd64e3ac6acb1b162e"
INFERENCE_DIRECTORY = "/mingli01/project/ht/patchalign-cpp/artifacts/data-v2/exploratory-formal/inference"
HOLDOUT_DIRECTORY = "/mingli01/data/patchalign-cpp/a3/formal-holdout-v1"
OUTPUT_DIRECTORY = f"{INFERENCE_DIRECTORY}/scoring-v2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong exploratory scoring config version")
    inference = config["inference"]
    require(inference["directory"] == INFERENCE_DIRECTORY, "wrong exploratory inference directory")
    require(inference["git_commit"] == INFERENCE_COMMIT, "wrong exploratory inference commit")
    require(
        inference["adapter_sha256"]
        == "sha256:d01dc411a2e67b9ad1e796433bce3836f07c2aa4d754e6976f47d1ab94421323",
        "wrong exploratory adapter",
    )
    require(
        inference["holdout_manifest_sha256"]
        == "sha256:5c438d36a0d4efc833dd6d0d26c67a1579f2c2e26de13f42ce01a809c07c3386",
        "wrong formal holdout",
    )
    expected_inference_hashes = {
        "config_sha256": "sha256:722a057aa30d77eec4b44511f38196f3c825a50797dd6ddae079a92e63abe3c4",
        "predictions_sha256": "sha256:4adcb5b7df160bcfcb941c38dbc19690db884badd5754b21d3d133df3cc4eabe",
        "run_manifest_sha256": "sha256:0d5bd0d1d0c0667412dc7a2485102538ba8de773ffc40e4eb392c8399ce2546b",
        "generation_summary_sha256": "sha256:2141632b0ccbd735fd2b027704e1ee12fffc3970949b8ede03de686d575e22dc",
        "determinism_probe_sha256": "sha256:e0678c116361cbc924136780017ab2e8e5268cb05fb8a0ec0f25609782bbccd8",
    }
    require(
        {key: inference[key] for key in expected_inference_hashes}
        == expected_inference_hashes,
        "inference artifact identities changed",
    )
    holdout = config["holdout"]
    require(holdout["directory"] == HOLDOUT_DIRECTORY, "wrong holdout directory")
    require(holdout["manifest"] == "a2-manifest.json", "wrong holdout manifest name")
    require(holdout["cases"] == 500, "wrong fixed denominator")
    require(
        holdout["task_level_counts"] == {"function": 400, "file_window": 100},
        "wrong holdout composition",
    )
    scoring = config["scoring"]
    require(scoring["protocol"] == "a3-scoring-v2", "wrong scoring protocol")
    require(scoring["config"] == "configs/evaluation/a3_scoring_v2.json", "wrong scoring config path")
    require(
        scoring["config_sha256"]
        == "sha256:b8d9507ec7fc97c370e52230759e0b2b84591d6fb4200a50944add19ebe859e8",
        "scoring config identity changed",
    )
    require(
        scoring["sandbox"] == "bubblewrap-0.12.0-rootless-no-network",
        "sandbox identity changed",
    )
    require(config["output_directory"] == OUTPUT_DIRECTORY, "wrong scoring output directory")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(),
        "exploratory scorer worktree is dirty",
    )
    require(args.bwrap.is_file() and args.bwrap.stat().st_mode & 0o111, "Bubblewrap missing or not executable")
    require(not args.report.exists(), f"refusing to overwrite scoring preflight: {args.report}")
    config = load_json(args.config)
    validate_config(config)
    scoring_config = repo / config["scoring"]["config"]
    require(
        sha256_file(scoring_config) == config["scoring"]["config_sha256"],
        "scoring v2 config hash mismatch",
    )

    inference = config["inference"]
    inference_dir = Path(inference["directory"])
    files = {
        "predictions.jsonl": inference["predictions_sha256"],
        "run-manifest.json": inference["run_manifest_sha256"],
        "generation-summary.json": inference["generation_summary_sha256"],
        "determinism-probe.json": inference["determinism_probe_sha256"],
    }
    for name, expected in files.items():
        path = inference_dir / name
        require(path.is_file(), f"missing inference artifact: {name}")
        require(sha256_file(path) == expected, f"inference artifact hash mismatch: {name}")

    run_manifest = load_json(inference_dir / "run-manifest.json")
    summary = load_json(inference_dir / "generation-summary.json")
    probes = load_json(inference_dir / "determinism-probe.json")
    require(run_manifest["git_commit"] == inference["git_commit"], "inference commit mismatch")
    require(run_manifest["config_sha256"] == inference["config_sha256"], "inference config mismatch")
    require(run_manifest["adapter_sha256"] == inference["adapter_sha256"], "inference adapter mismatch")
    require(
        run_manifest["dataset_manifest_sha256"] == inference["holdout_manifest_sha256"],
        "inference holdout mismatch",
    )
    require(
        run_manifest["prediction_artifact_sha256"] == inference["predictions_sha256"],
        "inference manifest prediction mismatch",
    )
    require(summary["cases"] == 500, "wrong generated denominator")
    require(summary["status_counts"] == {"ok": 500}, "generation failures present")
    require(summary["strict_diff_count"] == 498, "unexpected strict diff count")
    require(summary["determinism_probe_stable"] is True, "generation probe failed")
    require(len(probes) == 3 and all(item["stable"] for item in probes), "invalid determinism probes")

    holdout = config["holdout"]
    holdout_dir = Path(holdout["directory"])
    holdout_manifest_path = holdout_dir / holdout["manifest"]
    require(sha256_file(holdout_manifest_path) == inference["holdout_manifest_sha256"], "holdout hash mismatch")
    holdout_manifest = load_json(holdout_manifest_path)
    require(len(holdout_manifest["cases"]) == holdout["cases"], "holdout denominator mismatch")
    require(holdout_manifest["task_level_counts"] == holdout["task_level_counts"], "holdout task counts mismatch")

    prediction_schema = load_json(repo / "schemas/prediction-v0.1.schema.json")
    validator = Draft202012Validator(prediction_schema)
    predictions = [
        json.loads(line)
        for line in (inference_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    require(len(predictions) == holdout["cases"], "prediction denominator mismatch")
    expected_ids = [item["case_id"] for item in holdout_manifest["cases"]]
    require([item["sample_id"] for item in predictions] == expected_ids, "prediction order mismatch")
    for prediction in predictions:
        validator.validate(prediction)
        require(prediction["status"] == "ok", "non-ok prediction present")
        require(prediction["model"]["adapter_sha256"] == inference["adapter_sha256"], "prediction adapter mismatch")

    output_dir = Path(config["output_directory"])
    require(not output_dir.exists(), f"scoring output already exists: {output_dir}")
    report = {
        "version": "data-v2-exploratory-formal-scoring-preflight-v0.1",
        "status": "passed",
        "checked_at": utc_now(),
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "inference_git_commit": inference["git_commit"],
        "predictions_sha256": inference["predictions_sha256"],
        "holdout_manifest_sha256": inference["holdout_manifest_sha256"],
        "scoring_config_sha256": config["scoring"]["config_sha256"],
        "adapter_sha256": inference["adapter_sha256"],
        "cases": len(predictions),
        "task_level_counts": dict(Counter(item["task_level"] for item in holdout_manifest["cases"])),
        "strict_diff_count": summary["strict_diff_count"],
        "determinism_probe_count": len(probes),
        "output_dir_absent": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
