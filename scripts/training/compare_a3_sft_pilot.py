"""Audit and select between the frozen BF16 LoRA and NF4 QLoRA pilots."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from patchalign.evaluation.gates import load_quality_gate_config, select_pilot_candidate
from scripts.baseline.score_a3_baseline import summarize


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def score_counts(summary: dict[str, Any]) -> dict[str, int]:
    return {
        key: int(summary["all"]["counts"][key])
        for key in ("parse_success", "apply_success", "compile_success", "success")
    }


def audit_pilot(run_dir: Path, score_dir: Path, expected_mode: str) -> dict[str, Any]:
    training_manifest = load_json(run_dir / "training-manifest.json")
    training_summary = load_json(run_dir / "training-summary.json")
    inference_dir = run_dir / "inference"
    inference_manifest = load_json(inference_dir / "run-manifest.json")
    generation_summary = load_json(inference_dir / "generation-summary.json")
    predictions = load_jsonl(inference_dir / "predictions.jsonl")
    score_manifest = load_json(score_dir / "score-manifest.json")
    score_summary = load_json(score_dir / "score-summary.json")
    scores = load_jsonl(score_dir / "scores.jsonl")

    if training_summary["status"] != "completed" or training_summary["mode"] != expected_mode:
        raise RuntimeError(f"training summary is not completed {expected_mode}")
    if f"mode={expected_mode}" not in training_manifest["notes"]:
        raise RuntimeError(f"training manifest mode mismatch: {expected_mode}")
    if training_manifest["adapter_sha256"] != training_summary["adapter_sha256"]:
        raise RuntimeError(f"adapter hash mismatch: {expected_mode}")
    if inference_manifest["adapter_sha256"] != training_manifest["adapter_sha256"]:
        raise RuntimeError(f"inference adapter mismatch: {expected_mode}")
    if inference_manifest["git_commit"] != training_manifest["git_commit"]:
        raise RuntimeError(f"training/inference git mismatch: {expected_mode}")
    if inference_manifest["config_sha256"] != training_manifest["config_sha256"]:
        raise RuntimeError(f"training/inference config mismatch: {expected_mode}")
    if inference_manifest["prediction_artifact_sha256"] != sha256_file(
        inference_dir / "predictions.jsonl"
    ):
        raise RuntimeError(f"prediction hash mismatch: {expected_mode}")
    if len(predictions) != 70 or generation_summary["cases"] != 70:
        raise RuntimeError(f"frozen denominator mismatch: {expected_mode}")
    if generation_summary["status_counts"] != {
        "ok": 70,
        "generation_failed": 0,
        "timeout": 0,
        "oom": 0,
    }:
        raise RuntimeError(f"generation did not complete cleanly: {expected_mode}")
    if not generation_summary["determinism_probe_stable"]:
        raise RuntimeError(f"determinism probe failed: {expected_mode}")

    if score_manifest["schema_version"] != "0.2.0":
        raise RuntimeError(f"score manifest is not v0.2: {expected_mode}")
    if score_manifest["scoring_protocol_version"] != "a3-scoring-v2":
        raise RuntimeError(f"wrong scoring protocol: {expected_mode}")
    if score_manifest["source_inference_git_commit"] != inference_manifest["git_commit"]:
        raise RuntimeError(f"score source commit mismatch: {expected_mode}")
    if score_manifest["source_inference_config_sha256"] != inference_manifest["config_sha256"]:
        raise RuntimeError(f"score source config mismatch: {expected_mode}")
    if score_manifest["prediction_artifact_sha256"] != sha256_file(
        inference_dir / "predictions.jsonl"
    ):
        raise RuntimeError(f"score prediction hash mismatch: {expected_mode}")
    if score_manifest["execution_artifact_sha256"] != sha256_file(score_dir / "scores.jsonl"):
        raise RuntimeError(f"score artifact hash mismatch: {expected_mode}")
    if score_manifest["summary_artifact_sha256"] != sha256_file(
        score_dir / "score-summary.json"
    ):
        raise RuntimeError(f"score summary hash mismatch: {expected_mode}")
    if len(scores) != 70 or score_summary["all"]["counts"]["total"] != 70:
        raise RuntimeError(f"score denominator mismatch: {expected_mode}")
    if summarize(scores) != score_summary:
        raise RuntimeError(f"score summary does not recompute: {expected_mode}")
    if [x["sample_id"] for x in predictions] != [x["case_id"] for x in scores]:
        raise RuntimeError(f"prediction/score order mismatch: {expected_mode}")

    pipeline_seconds = (
        parse_time(inference_manifest["finished_at"])
        - parse_time(training_manifest["started_at"])
    ).total_seconds()
    peak_memory = max(
        int(training_summary["peak_gpu_memory_bytes"]),
        int(generation_summary["peak_gpu_memory_bytes"]),
    )
    return {
        "mode": expected_mode,
        "run_dir": run_dir,
        "score_dir": score_dir,
        "training_manifest": training_manifest,
        "training_summary": training_summary,
        "inference_manifest": inference_manifest,
        "generation_summary": generation_summary,
        "score_manifest": score_manifest,
        "score_summary": score_summary,
        "predictions": predictions,
        "pipeline_wall_time_seconds": pipeline_seconds,
        "peak_gpu_memory_bytes": peak_memory,
    }


def build_comparison(
    bf16_run_dir: Path,
    bf16_score_dir: Path,
    nf4_run_dir: Path,
    nf4_score_dir: Path,
    m0_score_dir: Path,
    quality_gates: Path,
) -> dict[str, Any]:
    runs = {
        "bf16_lora": audit_pilot(bf16_run_dir, bf16_score_dir, "bf16_lora"),
        "nf4_qlora": audit_pilot(nf4_run_dir, nf4_score_dir, "nf4_qlora"),
    }
    bf16 = runs["bf16_lora"]
    nf4 = runs["nf4_qlora"]
    for field in (
        "git_commit",
        "config_sha256",
        "model_id",
        "model_revision",
        "model_config_sha256",
        "dataset_manifest_sha256",
        "environment_sha256",
        "seed",
    ):
        if bf16["training_manifest"][field] != nf4["training_manifest"][field]:
            raise RuntimeError(f"training comparability mismatch: {field}")
    if (
        bf16["training_summary"]["training_order_sha256"]
        != nf4["training_summary"]["training_order_sha256"]
    ):
        raise RuntimeError("training order differs")
    for field in (
        "git_commit",
        "config_sha256",
        "scoring_config_sha256",
        "dataset_manifest_sha256",
        "seed",
    ):
        if bf16["score_manifest"][field] != nf4["score_manifest"][field]:
            raise RuntimeError(f"evaluation comparability mismatch: {field}")

    identities = {
        mode: [
            (x["sample_id"], x["prompt_version"], x["prompt_sha256"])
            for x in run["predictions"]
        ]
        for mode, run in runs.items()
    }
    if identities["bf16_lora"] != identities["nf4_qlora"]:
        raise RuntimeError("pilot evaluation prompt identity differs")

    m0_run_dir = m0_score_dir.parents[1]
    m0_predictions = load_jsonl(m0_run_dir / "predictions.jsonl")
    m0_identity = [
        (x["sample_id"], x["prompt_version"], x["prompt_sha256"])
        for x in m0_predictions
    ]
    if identities["bf16_lora"] != m0_identity:
        raise RuntimeError("pilot/M0 prompt identity differs")
    m0_manifest = load_json(m0_score_dir / "score-manifest.json")
    m0_summary = load_json(m0_score_dir / "score-summary.json")
    if m0_manifest["scoring_protocol_version"] != "a3-scoring-v2":
        raise RuntimeError("M0 does not use scoring v2")
    if (
        m0_manifest["dataset_manifest_sha256"]
        != bf16["score_manifest"]["dataset_manifest_sha256"]
    ):
        raise RuntimeError("pilot/M0 evaluation dataset differs")
    if (
        m0_manifest["scoring_config_sha256"]
        != bf16["score_manifest"]["scoring_config_sha256"]
    ):
        raise RuntimeError("pilot/M0 scoring config differs")

    gate_config = load_quality_gate_config(quality_gates)
    candidates = [
        {
            "name": mode,
            "completed": True,
            "stable": True,
            "success_count": score_counts(run["score_summary"])["success"],
            "peak_memory_bytes": run["peak_gpu_memory_bytes"],
            "wall_time_seconds": run["pipeline_wall_time_seconds"],
        }
        for mode, run in runs.items()
    ]
    selection = select_pilot_candidate(candidates, gate_config)
    m0_counts = score_counts(m0_summary)
    result: dict[str, Any] = {
        "version": "a3-sft-pilot-comparison-v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "interpretation": (
            "A3.2 executable training pilot selection only; not a formal SFT quality claim."
        ),
        "comparability": {
            "same_git_commit": True,
            "same_training_config": True,
            "same_train_validation_data": True,
            "same_training_order": True,
            "same_model_and_revision": True,
            "same_seed": True,
            "only_loading_mode_differs": True,
            "same_evaluation_dataset": True,
            "same_case_order_and_prompt": True,
            "same_scoring_protocol": True,
        },
        "m0_scoring_v2": {
            "score_dir": str(m0_score_dir),
            "counts": m0_counts,
            "scores_sha256": m0_manifest["execution_artifact_sha256"],
        },
        "candidates": {},
        "selection": selection,
    }
    for mode, run in runs.items():
        counts = score_counts(run["score_summary"])
        result["candidates"][mode] = {
            "run_dir": str(run["run_dir"]),
            "score_dir": str(run["score_dir"]),
            "counts": counts,
            "minus_m0": {key: counts[key] - m0_counts[key] for key in counts},
            "pipeline_wall_time_seconds": run["pipeline_wall_time_seconds"],
            "peak_gpu_memory_bytes": run["peak_gpu_memory_bytes"],
            "mean_train_loss": run["training_summary"]["mean_train_loss"],
            "mean_validation_loss": run["training_summary"]["mean_validation_loss"],
            "adapter_sha256": run["training_manifest"]["adapter_sha256"],
            "predictions_sha256": run["inference_manifest"]["prediction_artifact_sha256"],
            "scores_sha256": run["score_manifest"]["execution_artifact_sha256"],
            "summary_sha256": run["score_manifest"]["summary_artifact_sha256"],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bf16-run-dir", type=Path, required=True)
    parser.add_argument("--bf16-score-dir", type=Path, required=True)
    parser.add_argument("--nf4-run-dir", type=Path, required=True)
    parser.add_argument("--nf4-score-dir", type=Path, required=True)
    parser.add_argument("--m0-score-dir", type=Path, required=True)
    parser.add_argument("--quality-gates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite comparison: {args.output}")
    repo = Path(__file__).resolve().parents[2]
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repo, text=True
    ).strip():
        raise SystemExit("comparison worktree is dirty")
    result = build_comparison(
        args.bf16_run_dir,
        args.bf16_score_dir,
        args.nf4_run_dir,
        args.nf4_score_dir,
        args.m0_score_dir,
        args.quality_gates,
    )
    result["comparison_git_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "selection": result["selection"],
                "candidates": result["candidates"],
                "output": str(args.output),
                "sha256": sha256_file(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
