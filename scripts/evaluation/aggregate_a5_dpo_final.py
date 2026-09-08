#!/usr/bin/env python3
"""Aggregate selected-DPO final evaluation, gates, transitions, and failures."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from patchalign.evaluation.gates import paired_bootstrap_difference
from scripts.evaluation.a5_dpo_final_common import (
    DATASETS,
    BASELINE_ADAPTER_SHA,
    inference_dir,
    read_json,
    read_jsonl,
    scoring_dir,
    validate_config,
    verify_baseline,
    verify_dataset,
    verify_selection_and_adapter,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def row_timed_out(row: dict[str, Any]) -> bool:
    if "timed_out" in row:
        return bool(row["timed_out"])
    return any(
        stage.get("timed_out", False)
        or any(outcome.get("timed_out", False) for outcome in stage.get("outcomes", []))
        for stage in row.get("stages", {}).values()
    )


def cpp_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    classifications = Counter(row["terminal_classification"] for row in rows)
    return {
        "total": len(rows),
        "parse_success": sum(row["stages"]["parse"]["status"] == "passed" for row in rows),
        "apply_success": sum(row["stages"]["apply"]["status"] == "passed" for row in rows),
        "compile_success": sum(row["stages"]["build"]["status"] == "passed" for row in rows),
        "public_test_success": sum(row["stages"]["public"]["status"] == "passed" for row in rows),
        "hidden_test_success": sum(row["stages"]["hidden"]["status"] == "passed" for row in rows),
        "pass_at_1": sum(row["success"] for row in rows),
        "regression_failures": classifications["regression_failed"],
        "timeouts": sum(row_timed_out(row) for row in rows),
    }


def external_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "parse_success": sum(row["terminal_classification"] not in {"generation_failed", "parse_failed"} for row in rows),
        "apply_success": sum(bool(row.get("rootfs_result")) and row["rootfs_result"].get("stages", {}).get("apply", {}).get("returncode") == 0 for row in rows),
        "compile_success": sum(row["terminal_classification"] in {"success", "test_failed", "test_timeout"} for row in rows),
        "pass_at_1": sum(row["success"] for row in rows),
        "timeouts": sum(row_timed_out(row) for row in rows),
    }


def rates(counts: dict[str, int]) -> dict[str, float]:
    total = counts["total"]
    return {key: value / total for key, value in counts.items() if key != "total"}


def validate_candidate(config: dict[str, Any], name: str) -> tuple[list[dict], dict, dict]:
    directory = inference_dir(config, name)
    predictions_path = directory / "predictions.jsonl"
    predictions = read_jsonl(predictions_path)
    manifest = read_json(directory / "run-manifest.json")
    summary = read_json(directory / "generation-summary.json")
    dataset = config["datasets"][name]
    require(len(predictions) == dataset["case_count"], f"{name} candidate denominator changed")
    require(manifest["adapter_sha256"] == config["adapter"]["sha256"], f"{name} candidate adapter changed")
    require(manifest["dataset_manifest_sha256"] == dataset["manifest_sha256"], f"{name} candidate dataset changed")
    require(manifest["prediction_artifact_sha256"] == sha256_file(predictions_path), f"{name} predictions changed")
    require(summary["cases"] == dataset["case_count"], f"{name} generation denominator changed")
    require(summary["status_counts"] == {"ok": dataset["case_count"]}, f"{name} generation failures present")
    require(summary["determinism_probe_count"] == 3 and summary["determinism_probe_stable"] is True, f"{name} generation replay failed")
    return predictions, manifest, summary


def transitions(baseline: list[dict], candidate: list[dict]) -> dict[str, Any]:
    require([row["case_id"] for row in baseline] == [row["case_id"] for row in candidate], "paired score order changed")
    resolved = []
    introduced = []
    retained = []
    terminal_pairs = Counter()
    for before, after in zip(baseline, candidate, strict=True):
        case_id = before["case_id"]
        if after["success"] and not before["success"]:
            resolved.append(case_id)
        elif before["success"] and not after["success"]:
            introduced.append(case_id)
        elif before["success"] and after["success"]:
            retained.append(case_id)
        terminal_pairs[f"{before['terminal_classification']}->{after['terminal_classification']}"] += 1
    return {
        "resolved_failures": resolved,
        "introduced_failures": introduced,
        "retained_successes": retained,
        "terminal_transitions": dict(sorted(terminal_pairs.items())),
    }


def paired_ci(before: list[dict], after: list[dict], config: dict[str, Any]) -> dict[str, float]:
    bootstrap = read_json(Path(__file__).resolve().parents[2] / config["quality_gates"]["path"])["paired_bootstrap"]
    return paired_bootstrap_difference(
        [row["success"] for row in before],
        [row["success"] for row in after],
        confidence_level=bootstrap["confidence_level"],
        resamples=bootstrap["resamples"],
        seed=bootstrap["seed"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 final aggregation requires a clean worktree")
    require(not Path(config["outputs"]["comparison"]).exists(), "refusing to overwrite A5 final comparison")
    require(not Path(config["outputs"]["failure_analysis"]).exists(), "refusing to overwrite A5 failure analysis")
    verify_selection_and_adapter(config)
    for name in DATASETS:
        verify_dataset(config, name)
        verify_baseline(config, name)

    paired = {}
    failure = {}
    for name in ("formal", "confirmation"):
        dataset = config["datasets"][name]
        candidate_predictions, _, generation = validate_candidate(config, name)
        baseline_predictions = read_jsonl(Path(dataset["baseline"]["inference_directory"]) / "predictions.jsonl")
        require(
            [(row["sample_id"], row["prompt_version"], row["prompt_sha256"]) for row in baseline_predictions]
            == [(row["sample_id"], row["prompt_version"], row["prompt_sha256"]) for row in candidate_predictions],
            f"{name} prompt identities differ",
        )
        baseline_scores = read_jsonl(Path(dataset["baseline"]["scoring_directory"]) / "scores.jsonl")
        candidate_scores = read_jsonl(scoring_dir(config, name) / "scores.jsonl")
        require(len(baseline_scores) == len(candidate_scores) == dataset["case_count"], f"{name} score denominator changed")
        require([row["case_id"] for row in baseline_scores] == [row["case_id"] for row in candidate_scores], f"{name} score order changed")
        slices = {}
        for level in ("all", "function", "file_window"):
            before = baseline_scores if level == "all" else [row for row in baseline_scores if row["task_level"] == level]
            after = candidate_scores if level == "all" else [row for row in candidate_scores if row["task_level"] == level]
            before_counts, after_counts = cpp_counts(before), cpp_counts(after)
            slices[level] = {
                "baseline_counts": before_counts,
                "candidate_counts": after_counts,
                "baseline_rates": rates(before_counts),
                "candidate_rates": rates(after_counts),
                "pass_at_1_delta": rates(after_counts)["pass_at_1"] - rates(before_counts)["pass_at_1"],
                "paired_bootstrap": paired_ci(before, after, config),
            }
        paired[name] = {"generation": generation, "slices": slices}
        failure[name] = transitions(baseline_scores, candidate_scores)

    dataset = config["datasets"]["defects4c"]
    candidate_predictions, _, generation = validate_candidate(config, "defects4c")
    baseline_predictions = read_jsonl(Path(dataset["baseline"]["inference_directory"]) / "predictions.jsonl")
    require(
        [(row["sample_id"], row["prompt_version"], row["prompt_sha256"]) for row in baseline_predictions]
        == [(row["sample_id"], row["prompt_version"], row["prompt_sha256"]) for row in candidate_predictions],
        "Defects4C prompt identities differ",
    )
    baseline_scores = read_jsonl(Path(dataset["baseline"]["scoring_directory"]) / "scores-m1_r2.jsonl")
    candidate_scores = []
    progress = scoring_dir(config, "defects4c") / "cases"
    for index, case in enumerate(verify_dataset(config, "defects4c")[1]["cases"]):
        checkpoint = read_json(progress / f"{index:03d}.json")
        require(checkpoint["identity"]["index"] == index and checkpoint["identity"]["case"] == case, f"Defects4C checkpoint identity changed: {index}")
        require(checkpoint["identity"]["config_sha256"] == sha256_file(args.config), f"Defects4C checkpoint config changed: {index}")
        candidate_scores.append({"case_id": case["case_id"], **checkpoint["result"]})
    require([row["case_id"] for row in baseline_scores] == [row["case_id"] for row in candidate_scores], "Defects4C score order changed")
    output_scores = scoring_dir(config, "defects4c") / "scores.jsonl"
    output_scores.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in candidate_scores), encoding="utf-8", newline="\n")
    baseline_counts, candidate_counts = external_counts(baseline_scores), external_counts(candidate_scores)
    external_summary = {
        "version": "a5-dpo-defects4c-summary-v1",
        "baseline_counts": baseline_counts,
        "candidate_counts": candidate_counts,
        "baseline_rates": rates(baseline_counts),
        "candidate_rates": rates(candidate_counts),
        "pass_at_1_delta": rates(candidate_counts)["pass_at_1"] - rates(baseline_counts)["pass_at_1"],
        "paired_bootstrap": paired_ci(baseline_scores, candidate_scores, config),
        "generation": generation,
        "scores_sha256": sha256_file(output_scores),
    }
    write_json(scoring_dir(config, "defects4c") / "summary.json", external_summary)
    paired["defects4c"] = external_summary
    failure["defects4c"] = transitions(baseline_scores, candidate_scores)

    gates = read_json(repo / config["quality_gates"]["path"])
    maximum = gates["maximum_degradation"]
    formal = paired["formal"]["slices"]
    all_before = formal["all"]["baseline_rates"]
    all_after = formal["all"]["candidate_rates"]
    reasons = []
    if formal["function"]["pass_at_1_delta"] + 1e-12 < gates["primary_improvement"]["dpo_absolute"]:
        reasons.append("formal_function_improvement_below_threshold")
    if formal["function"]["paired_bootstrap"]["lower"] + 1e-12 < gates["primary_improvement"]["ci_lower_minimum"]:
        reasons.append("formal_function_ci_lower_below_zero")
    for metric in ("parse", "apply", "compile"):
        key = f"{metric}_success"
        if all_after[key] - all_before[key] + 1e-12 < -maximum[f"{metric}_rate"]:
            reasons.append(f"formal_{metric}_degradation_exceeded")
    if all_after["regression_failures"] - all_before["regression_failures"] - 1e-12 > maximum["regression_rate_increase"]:
        reasons.append("formal_regression_increase_exceeded")
    if all_after["timeouts"] - all_before["timeouts"] - 1e-12 > maximum["timeout_rate_increase"]:
        reasons.append("formal_timeout_increase_exceeded")
    if formal["file_window"]["pass_at_1_delta"] + 1e-12 < -maximum["file_window_pass_at_1"]:
        reasons.append("formal_file_window_degradation_exceeded")
    if external_summary["pass_at_1_delta"] + 1e-12 < -maximum["external_pass_at_1"]:
        reasons.append("defects4c_degradation_exceeded")
    gate_passed = not reasons
    result = {
        "version": "a5-dpo-final-comparison-v1",
        "created_at": utc_now(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "config_sha256": sha256_file(args.config),
        "selection_sha256": config["selection"]["sha256"],
        "baseline_adapter_sha256": BASELINE_ADAPTER_SHA,
        "candidate_adapter_sha256": config["adapter"]["sha256"],
        "results": paired,
        "dpo_gate_passed": gate_passed,
        "gate_reasons": reasons,
        "recommended_model": "dpo_beta03" if gate_passed else "m1_r2",
        "confirmation_role": "supplementary_unseen_diagnostic",
    }
    failure_document = {
        "version": "a5-dpo-final-failure-analysis-v1",
        "created_at": utc_now(),
        "config_sha256": sha256_file(args.config),
        "baseline": "m1_r2",
        "candidate": "dpo_beta03",
        "datasets": failure,
    }
    Path(config["outputs"]["comparison"]).parent.mkdir(parents=True, exist_ok=True)
    write_json(Path(config["outputs"]["comparison"]), result)
    write_json(Path(config["outputs"]["failure_analysis"]), failure_document)
    print(json.dumps({"dpo_gate_passed": gate_passed, "gate_reasons": reasons, "recommended_model": result["recommended_model"]}, sort_keys=True))


if __name__ == "__main__":
    main()
