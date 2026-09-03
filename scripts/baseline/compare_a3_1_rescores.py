"""Compare strict-v1 and terminal-LF-normalized A3.1 baseline scores."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from scripts.baseline.score_a3_baseline import (
    A31_SCORING_PROTOCOL,
    prepare_patch_text,
    sha256_bytes,
    summarize,
)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def counts(summary: dict[str, Any]) -> dict[str, int]:
    keys = ("parse_success", "apply_success", "compile_success", "success")
    return {key: int(summary["all"]["counts"][key]) for key in keys}


def audit_rescore(score_dir: Path) -> dict[str, Any]:
    run_dir = score_dir.parents[1]
    manifest = load_json(score_dir / "score-manifest.json")
    summary = load_json(score_dir / "score-summary.json")
    scores = load_jsonl(score_dir / "scores.jsonl")
    predictions = load_jsonl(run_dir / "predictions.jsonl")
    if manifest["schema_version"] != "0.2.0":
        raise RuntimeError(f"not an A3.1 score manifest: {score_dir}")
    if manifest["scoring_protocol_version"] != "a3-scoring-v2":
        raise RuntimeError(f"wrong scoring protocol: {score_dir}")
    if manifest["config_sha256"] != manifest["scoring_config_sha256"]:
        raise RuntimeError(f"config hash roles disagree: {score_dir}")
    if manifest["prediction_artifact_sha256"] != sha256_file(
        run_dir / "predictions.jsonl"
    ):
        raise RuntimeError(f"source prediction hash mismatch: {score_dir}")
    if manifest["execution_artifact_sha256"] != sha256_file(
        score_dir / "scores.jsonl"
    ):
        raise RuntimeError(f"score hash mismatch: {score_dir}")
    if manifest["summary_artifact_sha256"] != sha256_file(
        score_dir / "score-summary.json"
    ):
        raise RuntimeError(f"summary hash mismatch: {score_dir}")
    if len(scores) != len(predictions) or len(scores) != 70:
        raise RuntimeError(f"frozen denominator mismatch: {score_dir}")
    if [x["case_id"] for x in scores] != [x["sample_id"] for x in predictions]:
        raise RuntimeError(f"source order mismatch: {score_dir}")
    if any(x["scoring_protocol_version"] != "a3-scoring-v2" for x in scores):
        raise RuntimeError(f"mixed scoring protocols: {score_dir}")
    if summary["all"]["counts"]["total"] != 70:
        raise RuntimeError(f"summary denominator mismatch: {score_dir}")

    if summarize(scores) != summary:
        raise RuntimeError(f"score summary does not recompute: {score_dir}")
    for score, prediction in zip(scores, predictions):
        evaluated_text, terminal_lf_added = prepare_patch_text(
            prediction["raw_text"], A31_SCORING_PROTOCOL
        )
        if score["prediction_sha256"] != sha256_bytes(
            prediction["raw_text"].encode("utf-8")
        ):
            raise RuntimeError(f"per-case raw prediction hash mismatch: {score_dir}")
        if score["evaluated_patch_sha256"] != sha256_bytes(
            evaluated_text.encode("utf-8")
        ):
            raise RuntimeError(f"per-case evaluated patch hash mismatch: {score_dir}")
        normalization = score["transport_normalization"]
        if (
            normalization["terminal_lf_added"] != terminal_lf_added
            or normalization["added_bytes"] != int(terminal_lf_added)
        ):
            raise RuntimeError(f"per-case normalization audit mismatch: {score_dir}")

    return {
        "score_dir": str(score_dir),
        "run_dir": str(run_dir),
        "manifest": manifest,
        "summary": summary,
        "scores": scores,
        "predictions": predictions,
    }


def build_comparison(m0_score_dir: Path, external_score_dir: Path) -> dict[str, Any]:
    runs = {
        "m0": audit_rescore(m0_score_dir),
        "external": audit_rescore(external_score_dir),
    }
    m0 = runs["m0"]
    external = runs["external"]
    for field in (
        "git_commit",
        "config_sha256",
        "scoring_config_sha256",
        "source_inference_git_commit",
        "source_inference_config_sha256",
        "dataset_manifest_sha256",
        "seed",
    ):
        if m0["manifest"][field] != external["manifest"][field]:
            raise RuntimeError(f"A3.1 comparability mismatch: {field}")
    m0_identity = [
        (x["sample_id"], x["prompt_version"], x["prompt_sha256"])
        for x in m0["predictions"]
    ]
    external_identity = [
        (x["sample_id"], x["prompt_version"], x["prompt_sha256"])
        for x in external["predictions"]
    ]
    if m0_identity != external_identity:
        raise RuntimeError("A3.1 source prompt identity mismatch")

    result: dict[str, Any] = {
        "version": "a3.1-rescore-comparison-v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "interpretation": (
            "Protocol-correction rescore of immutable A3.0 predictions; "
            "not a model-quality or training comparison."
        ),
        "comparability": {
            "same_evaluator_git_commit": True,
            "same_scoring_config": True,
            "same_source_inference_git_commit": True,
            "same_source_inference_config": True,
            "same_dataset_manifest": True,
            "same_seed": True,
            "same_case_order_and_canonical_prompt": True,
            "raw_predictions_immutable": True,
        },
        "roles": {},
    }
    for role, run in runs.items():
        v1_summary = load_json(
            Path(run["run_dir"]) / "scoring" / "score-summary.json"
        )
        v1 = counts(v1_summary)
        v2 = counts(run["summary"])
        result["roles"][role] = {
            "model_id": run["manifest"]["model_id"],
            "source_prediction_sha256": run["manifest"][
                "prediction_artifact_sha256"
            ],
            "v1_strict_raw": v1,
            "v2_terminal_lf_normalized": v2,
            "v2_minus_v1": {key: v2[key] - v1[key] for key in v1},
            "terminal_lf_added": run["summary"]["transport_normalization"][
                "terminal_lf_added"
            ],
            "v2_scores_sha256": run["manifest"]["execution_artifact_sha256"],
            "v2_summary_sha256": run["manifest"]["summary_artifact_sha256"],
            "score_dir": run["score_dir"],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m0-score-dir", type=Path, required=True)
    parser.add_argument("--external-score-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite comparison: {args.output}")
    repo = Path(__file__).resolve().parents[2]
    comparison_git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repo, text=True
    ).strip():
        raise SystemExit("comparison worktree is dirty")
    result = build_comparison(args.m0_score_dir, args.external_score_dir)
    result["comparison_git_commit"] = comparison_git_commit
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "roles": result["roles"],
                "sha256": sha256_file(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
