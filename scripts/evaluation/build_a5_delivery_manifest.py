#!/usr/bin/env python3
"""Build a hash-complete index for the final PatchAlign-Cpp A5 delivery."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from scripts.evaluation.a5_dpo_final_common import (
    DATASETS,
    inference_dir,
    read_json,
    scoring_dir,
    validate_config,
    verify_selection_and_adapter,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json


BASELINE_ADAPTER_DIR = Path(
    "/mingli01/project/ht/patchalign-cpp/artifacts/a3/sft-r2/training/"
    "checkpoints/checkpoint-step-000150-epoch-1/adapter"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def entry(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing delivery artifact: {path}")
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "delivery manifest requires a clean worktree")
    require(not args.output.exists(), "refusing to overwrite delivery manifest")
    verify_selection_and_adapter(config)
    comparison = read_json(Path(config["outputs"]["comparison"]))
    failure = read_json(Path(config["outputs"]["failure_analysis"]))
    require(comparison["version"] == "a5-dpo-final-comparison-v1", "wrong final comparison version")
    require(comparison["config_sha256"] == sha256_file(args.config), "final comparison config changed")
    require(failure["config_sha256"] == sha256_file(args.config), "failure analysis config changed")

    artifacts: dict[str, dict[str, Any]] = {
        "evaluation_config": entry(args.config),
        "selection": entry(Path(config["selection"]["path"])),
        "baseline_adapter": entry(BASELINE_ADAPTER_DIR / "adapter_model.safetensors"),
        "baseline_adapter_config": entry(BASELINE_ADAPTER_DIR / "adapter_config.json"),
        "dpo_candidate_adapter": entry(Path(config["adapter"]["path"]) / "adapter_model.safetensors"),
        "dpo_candidate_adapter_config": entry(Path(config["adapter"]["path"]) / "adapter_config.json"),
        "dpo_training_manifest": entry(Path(config["adapter"]["training_manifest"])),
        "dpo_training_summary": entry(Path(config["adapter"]["training_summary"])),
        "final_preflight": entry(Path(config["outputs"]["preflight"])),
        "final_comparison": entry(Path(config["outputs"]["comparison"])),
        "failure_analysis": entry(Path(config["outputs"]["failure_analysis"])),
        "environment_lock": entry(Path(config["environment"]["lock"])),
        "base_config": entry(Path(config["model"]["local_path"]) / "config.json"),
    }
    require(
        artifacts["baseline_adapter"]["sha256"] == comparison["baseline_adapter_sha256"],
        "baseline adapter changed since final evaluation",
    )
    require(
        artifacts["dpo_candidate_adapter"]["sha256"] == comparison["candidate_adapter_sha256"],
        "DPO candidate adapter changed since final evaluation",
    )
    for name in DATASETS:
        inference = inference_dir(config, name)
        for filename in ("prompts.jsonl", "predictions.jsonl", "generation-summary.json", "determinism-probe.json", "run-manifest.json"):
            artifacts[f"{name}_inference_{filename}"] = entry(inference / filename)
        scoring = scoring_dir(config, name)
        filenames = ("scores.jsonl", "summary.json") if name == "defects4c" else ("scores.jsonl", "score-summary.json", "score-manifest.json")
        for filename in filenames:
            artifacts[f"{name}_scoring_{filename}"] = entry(scoring / filename)

    recommended_adapter_artifact_key = (
        "dpo_candidate_adapter" if comparison["recommended_model"] == "dpo_beta03" else "baseline_adapter"
    )
    result = {
        "version": "patchalign-cpp-delivery-manifest-v1",
        "created_at": utc_now(),
        "delivery_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "evaluation_git_commit": comparison["git_commit"],
        "recommended_model": comparison["recommended_model"],
        "recommended_adapter_artifact_key": recommended_adapter_artifact_key,
        "dpo_gate_passed": comparison["dpo_gate_passed"],
        "base": {"model_id": config["model"]["model_id"], "revision": config["model"]["revision"]},
        "baseline_adapter_sha256": comparison["baseline_adapter_sha256"],
        "candidate_adapter_sha256": comparison["candidate_adapter_sha256"],
        "dataset_manifest_sha256": {name: config["datasets"][name]["manifest_sha256"] for name in DATASETS},
        "artifacts": artifacts,
        "public_release_authorized": False,
        "notes": "Large weights/data remain internal; this index records identities and does not grant redistribution rights.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "recommended_model": result["recommended_model"],
                "recommended_adapter_artifact_key": recommended_adapter_artifact_key,
                "dpo_gate_passed": result["dpo_gate_passed"],
                "artifact_count": len(artifacts),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
