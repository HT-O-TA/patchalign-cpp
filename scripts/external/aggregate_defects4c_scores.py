"""Aggregate paired Defects4C executions and evaluate the frozen external gate."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from patchalign.evaluation.gates import paired_bootstrap_difference
from scripts.external.a3_defects4c_external_common import (
    ADAPTER_SHA,
    load_json,
    validate_config,
    verify_dataset,
    verify_predictions,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def summarize(rows: list[dict]) -> dict:
    classifications = Counter(row["terminal_classification"] for row in rows)
    total = len(rows)
    counts = {
        "total": total,
        "parse_success": sum(row["terminal_classification"] not in {"generation_failed", "parse_failed"} for row in rows),
        "policy_success": sum(row["terminal_classification"] not in {"generation_failed", "parse_failed", "policy_violation"} for row in rows),
        "apply_success": sum(
            bool(row.get("rootfs_result"))
            and row["rootfs_result"].get("stages", {}).get("apply", {}).get("returncode") == 0
            for row in rows
        ),
        "build_success": sum(row["terminal_classification"] in {"success", "test_failed", "test_timeout"} for row in rows),
        "test_pass_at_1": sum(row["success"] for row in rows),
        "timeouts": sum(row["timed_out"] for row in rows),
    }
    return {
        "counts": counts,
        "rates": {key: value / total for key, value in counts.items() if key != "total"},
        "terminal_classifications": dict(sorted(classifications.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "external aggregation requires a clean worktree")
    config = load_json(args.config)
    validate_config(config)
    manifest, _ = verify_dataset(config)
    output = Path(config["scoring"]["output_directory"])
    require(not output.exists(), "refusing to overwrite external score output")
    inference = {}
    for role in ("m0", "m1_r2"):
        directory, predictions, run_manifest = verify_predictions(config, role)
        generation = load_json(directory / "generation-summary.json")
        require(generation["cases"] == manifest["case_count"], f"{role} generation count mismatch")
        require(generation["determinism_probe_stable"], f"{role} determinism probe failed")
        require(generation["status_counts"].get("ok") == manifest["case_count"], f"{role} generation not all ok")
        expected_adapter = None if role == "m0" else ADAPTER_SHA
        require(run_manifest["adapter_sha256"] == expected_adapter, f"{role} adapter mismatch")
        inference[role] = {"directory": directory, "predictions": predictions, "manifest": run_manifest, "generation": generation}

    rows = {"m0": [], "m1_r2": []}
    progress = Path(config["scoring"]["progress_directory"])
    for index, case in enumerate(manifest["cases"]):
        checkpoint = progress / "cases" / f"{index:03d}.json"
        require(checkpoint.is_file(), f"missing external score checkpoint: {index}")
        value = load_json(checkpoint)
        require(value["identity"]["index"] == index and value["identity"]["case"] == case, f"external score checkpoint identity mismatch: {index}")
        require(value["identity"]["config_sha256"] == sha256_file(args.config), f"external score config mismatch: {index}")
        for role in rows:
            result = value["results"][role]
            require(result["case_id"] == case["case_id"] and result["role"] == role, f"external result identity mismatch: {index}/{role}")
            rows[role].append({
                "case_id": case["case_id"],
                "project": case["project"],
                "commit_after": case["commit_after"],
                "source_file": case["source_file"],
                **result,
            })
    summaries = {role: summarize(values) for role, values in rows.items()}
    baseline = [row["success"] for row in rows["m0"]]
    candidate = [row["success"] for row in rows["m1_r2"]]
    delta = sum(candidate) / len(candidate) - sum(baseline) / len(baseline)
    threshold = config["quality_gates"]["external_pass_at_1_maximum_degradation"]
    reasons = []
    if delta + 1e-12 < -threshold:
        reasons.append("external_pass_at_1_degradation_exceeded")
    bootstrap = paired_bootstrap_difference(
        baseline,
        candidate,
        confidence_level=0.95,
        resamples=10000,
        seed=config["seed"],
    )
    transitions = {
        "introduced": [case["case_id"] for case, before, after in zip(manifest["cases"], baseline, candidate, strict=True) if after and not before],
        "resolved": [case["case_id"] for case, before, after in zip(manifest["cases"], baseline, candidate, strict=True) if before and not after],
        "retained": [case["case_id"] for case, before, after in zip(manifest["cases"], baseline, candidate, strict=True) if before and after],
    }
    output.mkdir(parents=True)
    for role, values in rows.items():
        (output / f"scores-{role}.jsonl").write_text(
            "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values),
            encoding="utf-8",
        )
        write_json(output / f"summary-{role}.json", summaries[role])
    comparison = {
        "version": "a3-defects4c-external-comparison-v1",
        "created_at": utc_now(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "config_sha256": sha256_file(args.config),
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "denominator": len(baseline),
        "counts": {role: summaries[role]["counts"] for role in summaries},
        "external_pass_at_1_delta": delta,
        "maximum_allowed_degradation": threshold,
        "paired_bootstrap": bootstrap,
        "transitions": transitions,
        "external_gate_passed": not reasons,
        "reasons": reasons,
    }
    write_json(output / "comparison.json", comparison)
    artifact_hashes = {
        path.name: sha256_file(path)
        for path in sorted(output.iterdir())
        if path.is_file()
    }
    manifest_out = {
        "version": "a3-defects4c-external-artifacts-v1",
        "created_at": utc_now(),
        "slurm_job_id": __import__("os").environ.get("SLURM_JOB_ID"),
        "config_sha256": sha256_file(args.config),
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "input_prediction_hashes": {role: data["manifest"]["prediction_artifact_sha256"] for role, data in inference.items()},
        "artifact_hashes": artifact_hashes,
        "external_gate_passed": comparison["external_gate_passed"],
    }
    write_json(output / "artifact-manifest.json", manifest_out)
    print(json.dumps({"external_gate_passed": comparison["external_gate_passed"], "reasons": reasons, "denominator": len(baseline), "counts": comparison["counts"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
