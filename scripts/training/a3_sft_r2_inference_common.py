"""Fail-closed binding checks for A3.4/SFT-R2 inference artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file


VERSION = "a3-sft-r2-inference-v1"
TRAINING_VERSION = "a3-sft-r2-training-v1"
TRAINING_MANIFEST_COMMIT = "8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c"
MODEL_REVISION = "0396a76181e127dfc13e5c5ec48a8cee09938b02"


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong R2 inference config version")
    require(config.get("run_id") == "a34_m1_r2_nf4_s20260830", "wrong R2 run id")
    require(config.get("seed") == 20260830, "wrong R2 inference seed")
    model = config["model"]
    require(model["model_id"] == "Qwen/Qwen2.5-Coder-7B", "wrong model id")
    require(model["revision"] == MODEL_REVISION, "wrong model revision")
    require(model["config_sha256"].startswith("sha256:"), "model hash missing")

    source = config["source_training"]
    require(source["git_commit"] == TRAINING_MANIFEST_COMMIT, "wrong R2 training commit")
    require(
        source["checkpoint"] == "checkpoints/checkpoint-step-000150-epoch-1",
        "wrong R2 inference checkpoint",
    )
    for key in (
        "config_sha256",
        "selection_manifest_sha256",
        "manifest_sha256",
        "summary_sha256",
        "best_checkpoint_sha256",
        "adapter_sha256",
        "source_adapter_sha256",
    ):
        require(source[key].startswith("sha256:"), f"missing source hash: {key}")

    evaluation = config["evaluation"]
    require(
        evaluation["holdout_manifest"] == "a2-manifest.json",
        "wrong holdout manifest name",
    )
    require(
        evaluation["holdout_manifest_sha256"]
        == "sha256:5c438d36a0d4efc833dd6d0d26c67a1579f2c2e26de13f42ce01a809c07c3386",
        "formal holdout identity changed",
    )
    require(
        evaluation["prompt_artifact_sha256"]
        == "sha256:1a1c8cb2c827c6c6325db798991bb3c9b66241520ae70520cdbdd18e6188ba1f",
        "formal prompt artifact identity changed",
    )
    require(
        evaluation["required_task_levels"] == {"function": 400, "file_window": 100},
        "wrong holdout composition",
    )
    require(evaluation["prompt_version"] == "a3-cpp-repair-v1", "wrong prompt version")
    require(evaluation["input_mode"] == "raw_completion", "wrong input mode")
    require(evaluation["allowed_path"] == "main.cpp", "wrong allowed path")
    require(evaluation["scoring_protocol"] == "a3-scoring-v2", "wrong scoring protocol")
    require(
        evaluation["generation"]
        == {
            "do_sample": False,
            "temperature": None,
            "top_p": None,
            "num_return_sequences": 1,
            "max_input_tokens": 4096,
            "max_new_tokens": 512,
        },
        "R2 inference generation settings changed",
    )


def verify_training_artifact(config: dict[str, Any]) -> dict[str, Any]:
    source = config["source_training"]
    root = Path(source["directory"])
    manifest_path = root / "training-manifest.json"
    summary_path = root / "training-summary.json"
    best_path = root / "best-checkpoint.json"
    for path in (manifest_path, summary_path, best_path):
        require(path.is_file(), f"missing R2 training artifact: {path.name}")
    require(sha256_file(manifest_path) == source["manifest_sha256"], "R2 training manifest hash mismatch")
    require(sha256_file(summary_path) == source["summary_sha256"], "R2 training summary hash mismatch")
    require(sha256_file(best_path) == source["best_checkpoint_sha256"], "R2 best checkpoint hash mismatch")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    best = json.loads(best_path.read_text(encoding="utf-8"))
    require(manifest["git_commit"] == source["git_commit"], "R2 training commit mismatch")
    require(manifest["config_sha256"] == source["config_sha256"], "R2 training config mismatch")
    require(
        manifest["dataset_manifest_sha256"] == source["selection_manifest_sha256"],
        "R2 selection manifest mismatch",
    )
    require(manifest["adapter_sha256"] == source["adapter_sha256"], "R2 manifest adapter mismatch")
    require(summary["version"] == TRAINING_VERSION, "wrong R2 training summary version")
    require(summary["status"] == "completed", "R2 training did not complete")
    require(summary["optimizer_steps"] == 150, "wrong R2 optimizer-step count")
    require(summary["train_examples"] == 1200, "wrong R2 train count")
    require(summary["validation_examples"] == 117, "wrong R2 validation count")
    require(summary["reference_validation_examples"] == 500, "wrong reference validation count")
    require(summary["best_adapter_sha256"] == source["adapter_sha256"], "R2 summary adapter mismatch")
    require(
        summary["source_adapter_sha256"] == source["source_adapter_sha256"],
        "R2 source adapter mismatch",
    )
    require(best["checkpoint"] == source["checkpoint"], "R2 best checkpoint path mismatch")
    require(best["optimizer_step"] == 150 and best["epoch"] == 1, "wrong R2 best checkpoint step")

    checkpoint = Path(source["checkpoint"])
    require(not checkpoint.is_absolute() and ".." not in checkpoint.parts, "unsafe checkpoint path")
    adapter_dir = root / checkpoint / "adapter"
    weights = adapter_dir / "adapter_model.safetensors"
    require(weights.is_file(), "R2 adapter weights missing")
    require(sha256_file(weights) == source["adapter_sha256"], "R2 adapter weights hash mismatch")
    require((adapter_dir / "adapter_config.json").is_file(), "R2 adapter config missing")
    return {
        "root": root,
        "adapter_dir": adapter_dir,
        "manifest": manifest,
        "summary": summary,
        "best": best,
    }


def verify_holdout_manifest(config: dict[str, Any]) -> Path:
    evaluation = config["evaluation"]
    path = Path(evaluation["holdout_root"]) / evaluation["holdout_manifest"]
    require(path.is_file(), "formal holdout manifest missing")
    require(
        sha256_file(path) == evaluation["holdout_manifest_sha256"],
        "formal holdout manifest hash mismatch",
    )
    return path
