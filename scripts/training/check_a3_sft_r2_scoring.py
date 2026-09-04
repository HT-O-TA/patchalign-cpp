"""Fail-closed artifact preflight for A3.4/SFT-R2 scoring v2."""

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


VERSION = "a3-sft-r2-scoring-v1"
INFERENCE_COMMIT = "84fb9dfe06c4530b8fab32d03ef3e15d803a94e7"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong R2 scoring config version")
    inference = config["inference"]
    require(inference["git_commit"] == INFERENCE_COMMIT, "wrong R2 inference commit")
    require(
        inference["adapter_sha256"]
        == "sha256:8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a",
        "wrong R2 adapter",
    )
    require(
        inference["holdout_manifest_sha256"]
        == "sha256:5c438d36a0d4efc833dd6d0d26c67a1579f2c2e26de13f42ce01a809c07c3386",
        "wrong formal holdout",
    )
    expected_inference_hashes = {
        "config_sha256": "sha256:d2ceed71424b89002e8774b500b9fe00020f54635119a7b05465e5590c2df07e",
        "predictions_sha256": "sha256:c5fe4e6d90d59c24f749949c8df4f074e2b26f6af625e960ce95013367e7bb6a",
        "run_manifest_sha256": "sha256:88abe6053202e8b81e0332166c3e6b66fefca3e50a0f36b39cdffae086983878",
        "generation_summary_sha256": "sha256:eb82f96cef4c103a4944f888f0d171307f1a25d3b35b15d780d5c18b1d26c09a",
        "determinism_probe_sha256": "sha256:3176c6a73d397561b75a3215a74380626dc290e4c41fc67111999202d790a38a",
    }
    require(
        {key: inference[key] for key in expected_inference_hashes}
        == expected_inference_hashes,
        "inference artifact identities changed",
    )
    holdout = config["holdout"]
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
        "R2 scorer worktree is dirty",
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
    require(summary["strict_diff_count"] == 499, "unexpected strict diff count")
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
        "version": "a3-sft-r2-scoring-preflight-v1",
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
