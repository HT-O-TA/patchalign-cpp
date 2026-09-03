"""Compare frozen M0 and external A3.0 baseline artifacts without attribution claims."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def success_counts(summary: dict[str, Any]) -> dict[str, int]:
    return {
        name: int(summary[name]["counts"]["success"])
        for name in ("all", "function", "file_window")
    }


def build_comparison(m0_dir: Path, external_dir: Path) -> dict[str, Any]:
    m0_manifest = load_json(m0_dir / "run-manifest.json")
    external_manifest = load_json(external_dir / "run-manifest.json")
    for field in (
        "git_commit",
        "config_sha256",
        "dataset_manifest_sha256",
        "seed",
    ):
        if m0_manifest[field] != external_manifest[field]:
            raise RuntimeError(f"baseline comparability mismatch: {field}")

    m0_generation = load_json(m0_dir / "generation-summary.json")
    external_generation = load_json(external_dir / "generation-summary.json")
    if not m0_generation["determinism_probe_stable"]:
        raise RuntimeError("M0 determinism probe failed")
    if not external_generation["determinism_probe_stable"]:
        raise RuntimeError("external determinism probe failed")

    m0_predictions = load_jsonl(m0_dir / "predictions.jsonl")
    external_predictions = load_jsonl(external_dir / "predictions.jsonl")
    m0_identity = [
        (record["sample_id"], record["prompt_version"], record["prompt_sha256"])
        for record in m0_predictions
    ]
    external_identity = [
        (record["sample_id"], record["prompt_version"], record["prompt_sha256"])
        for record in external_predictions
    ]
    if m0_identity != external_identity:
        raise RuntimeError("sample order, prompt version, or canonical prompt hash differs")

    m0_score_manifest = load_json(m0_dir / "scoring" / "score-manifest.json")
    external_score_manifest = load_json(
        external_dir / "scoring" / "score-manifest.json"
    )
    for run_dir, score_manifest in (
        (m0_dir, m0_score_manifest),
        (external_dir, external_score_manifest),
    ):
        if score_manifest["prediction_artifact_sha256"] != sha256_file(
            run_dir / "predictions.jsonl"
        ):
            raise RuntimeError(f"score manifest prediction hash mismatch: {run_dir}")
        if score_manifest["execution_artifact_sha256"] != sha256_file(
            run_dir / "scoring" / "scores.jsonl"
        ):
            raise RuntimeError(f"score manifest execution hash mismatch: {run_dir}")

    m0_summary = load_json(m0_dir / "scoring" / "score-summary.json")
    external_summary = load_json(
        external_dir / "scoring" / "score-summary.json"
    )
    if m0_summary["all"]["counts"]["total"] != 70:
        raise RuntimeError("M0 denominator is not the frozen 70 cases")
    if external_summary["all"]["counts"]["total"] != 70:
        raise RuntimeError("external denominator is not the frozen 70 cases")

    m0_success = success_counts(m0_summary)
    external_success = success_counts(external_summary)
    return {
        "version": "a3-baseline-comparison-v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "interpretation": (
            "A3.0 executable pilot baseline only; external capability is not "
            "attributable to PatchAlign-Cpp training."
        ),
        "comparability": {
            "same_git_commit": True,
            "same_config": True,
            "same_dataset_manifest": True,
            "same_seed": True,
            "same_case_order": True,
            "same_prompt_version_and_canonical_text": True,
            "m0_input_mode": "raw_completion",
            "external_input_mode": "chat_non_thinking",
            "generation_budget": {
                "do_sample": False,
                "max_input_tokens": 4096,
                "max_new_tokens": 512,
                "num_return_sequences": 1,
            },
        },
        "m0": {
            "model_id": m0_manifest["model_id"],
            "run_id": m0_manifest["run_id"],
            "run_dir": str(m0_dir),
            "prediction_sha256": sha256_file(m0_dir / "predictions.jsonl"),
            "scores_sha256": sha256_file(m0_dir / "scoring" / "scores.jsonl"),
            "success": m0_success,
            "generation": m0_generation,
            "score": m0_summary,
        },
        "external": {
            "model_id": external_manifest["model_id"],
            "run_id": external_manifest["run_id"],
            "run_dir": str(external_dir),
            "prediction_sha256": sha256_file(
                external_dir / "predictions.jsonl"
            ),
            "scores_sha256": sha256_file(
                external_dir / "scoring" / "scores.jsonl"
            ),
            "success": external_success,
            "generation": external_generation,
            "score": external_summary,
        },
        "external_minus_m0_success": {
            name: external_success[name] - m0_success[name]
            for name in m0_success
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m0-dir", type=Path, required=True)
    parser.add_argument("--external-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite comparison: {args.output}")
    result = build_comparison(args.m0_dir, args.external_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "m0_success": result["m0"]["success"],
                "external_success": result["external"]["success"],
                "external_minus_m0_success": result["external_minus_m0_success"],
                "output": str(args.output),
                "sha256": sha256_file(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
