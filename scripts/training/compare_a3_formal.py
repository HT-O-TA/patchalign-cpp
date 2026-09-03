"""Compare A3.3 M0 and SFT scores under the frozen quality gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from patchalign.evaluation.gates import (
    MetricSnapshot,
    evaluate_training_gate,
    load_quality_gate_config,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def snapshot(score_dir: Path, inference_dir: Path) -> tuple[MetricSnapshot, dict, list[dict]]:
    summary = load_json(score_dir / "score-summary.json")
    scores = load_jsonl(score_dir / "scores.jsonl")
    predictions = load_jsonl(inference_dir / "predictions.jsonl")
    score_manifest = load_json(score_dir / "score-manifest.json")
    inference_manifest = load_json(inference_dir / "run-manifest.json")
    require(len(scores) == len(predictions) == 500, "formal denominator must be 500")
    require(
        [item["case_id"] for item in scores] == [item["sample_id"] for item in predictions],
        "prediction/score order mismatch",
    )
    require(
        score_manifest["prediction_artifact_sha256"]
        == sha256_file(inference_dir / "predictions.jsonl"),
        "score prediction hash mismatch",
    )
    require(
        score_manifest["dataset_manifest_sha256"]
        == inference_manifest["dataset_manifest_sha256"],
        "score/inference dataset mismatch",
    )
    function = tuple(item["success"] for item in scores if item["task_level"] == "function")
    file_window = tuple(item["success"] for item in scores if item["task_level"] == "file_window")
    require(len(function) == 400 and len(file_window) == 100, "formal slice denominator mismatch")
    all_rates = summary["all"]["rates"]
    violations = []
    generation_summary = load_json(inference_dir / "generation-summary.json")
    if generation_summary["status_counts"].get("ok", 0) != 500:
        violations.append("generation_status_not_all_ok")
    if not generation_summary["determinism_probe_stable"]:
        violations.append("generation_determinism_probe_failed")
    return (
        MetricSnapshot(
            function_pass_at_1=function,
            file_window_pass_at_1=file_window,
            external_pass_at_1=(),
            parse_rate=all_rates["parse_success"],
            apply_rate=all_rates["apply_success"],
            compile_rate=all_rates["compile_success"],
            regression_rate=all_rates["regression_failures"],
            timeout_rate=all_rates["timeouts"],
            validity_violations=tuple(violations),
        ),
        summary,
        predictions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m0-inference", type=Path, required=True)
    parser.add_argument("--m0-score", type=Path, required=True)
    parser.add_argument("--sft-inference", type=Path, required=True)
    parser.add_argument("--sft-score", type=Path, required=True)
    parser.add_argument("--quality-gates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), f"refusing to overwrite comparison: {args.output}")
    baseline, m0_summary, m0_predictions = snapshot(args.m0_score, args.m0_inference)
    candidate, sft_summary, sft_predictions = snapshot(args.sft_score, args.sft_inference)
    require(
        [
            (item["sample_id"], item["prompt_version"], item["prompt_sha256"])
            for item in m0_predictions
        ]
        == [
            (item["sample_id"], item["prompt_version"], item["prompt_sha256"])
            for item in sft_predictions
        ],
        "M0/SFT prompt identity mismatch",
    )
    gate = evaluate_training_gate(
        "sft", baseline, candidate, load_quality_gate_config(args.quality_gates)
    )
    non_external_reasons = [
        reason for reason in gate["reasons"] if reason != "external_denominator_mismatch"
    ]
    result = {
        "version": "a3-formal-sft-comparison-v1",
        "full_promotion_gate_passed": gate["passed"],
        "internal_gate_passed": not non_external_reasons,
        "external_gate_status": "not_evaluated",
        "external_gate_requirement": "Defects4C >=150 paired cases",
        "internal_gate_reasons": non_external_reasons,
        "gate": gate,
        "m0_summary": m0_summary,
        "sft_summary": sft_summary,
        "artifacts": {
            "m0_scores_sha256": sha256_file(args.m0_score / "scores.jsonl"),
            "sft_scores_sha256": sha256_file(args.sft_score / "scores.jsonl"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(json.dumps({
        "full_promotion_gate_passed": result["full_promotion_gate_passed"],
        "internal_gate_passed": result["internal_gate_passed"],
        "reasons": gate["reasons"],
        "output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
