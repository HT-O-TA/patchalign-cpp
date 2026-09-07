"""Fail-closed binding checks for Data-v2 exploratory formal inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file


VERSION = "data-v2-exploratory-formal-inference-v0.1"
TRAINING_VERSION = "data-v2-exploratory-replay-training-result-v0.1"
TRAINING_MANIFEST_COMMIT = "53329624ddc2ce764b8b7acbf133d6e12682be16"
MODEL_REVISION = "0396a76181e127dfc13e5c5ec48a8cee09938b02"


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong exploratory inference config version")
    require(config.get("run_id") == "dv2_exploratory_formal_s20260906", "wrong exploratory run id")
    require(config.get("seed") == 20260906, "wrong exploratory inference seed")
    model = config["model"]
    require(model == {
        "model_id": "Qwen/Qwen2.5-Coder-7B",
        "local_path": "/mingli01/models/Qwen2.5-Coder-7B",
        "revision": MODEL_REVISION,
        "config_sha256": "sha256:4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605",
    }, "model identity changed")

    source = config["source_training"]
    require(source == {
        "directory": "/mingli01/project/ht/patchalign-cpp/artifacts/data-v2/exploratory-replay-training",
        "git_commit": TRAINING_MANIFEST_COMMIT,
        "config_sha256": "sha256:8fd855eefb83c1ae47df0698a85d186673c7c18d5eadb78f0e63e9a2502707e5",
        "selection_manifest_sha256": "sha256:5852bf9b6bfa091af7dd5b3cfb6ef2bfaa84d1aed07478454af9978ba79f083c",
        "manifest_sha256": "sha256:3feb8f6c8b3e1b8a61bfe15f61ae16f7abc34da52c8698312a8c0f710ef60a8b",
        "summary_sha256": "sha256:23df309cab3b6cbebb41f6afed1b075114e0f9cdeaf56bac96ee7e6edd20ac5a",
        "best_checkpoint_sha256": "sha256:5dff61e8f1d76cd0ed32197b04ebde7ebf5e83493e450d0fc70c8bd41626f6c9",
        "checkpoint": "checkpoints/checkpoint-step-000098-epoch-1",
        "adapter_sha256": "sha256:d01dc411a2e67b9ad1e796433bce3836f07c2aa4d754e6976f47d1ab94421323",
        "source_adapter_sha256": "sha256:8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a",
    }, "exploratory training identity changed")

    evaluation = config["evaluation"]
    expected_evaluation = {
        "manifest": "a2-manifest.json",
        "manifest_sha256": "sha256:5c438d36a0d4efc833dd6d0d26c67a1579f2c2e26de13f42ce01a809c07c3386",
        "prompt_sha256": "sha256:1a1c8cb2c827c6c6325db798991bb3c9b66241520ae70520cdbdd18e6188ba1f",
        "counts": {"function": 400, "file_window": 100},
    }
    require(evaluation["holdout_manifest"] == expected_evaluation["manifest"], "wrong holdout manifest name")
    require(evaluation["holdout_manifest_sha256"] == expected_evaluation["manifest_sha256"], "holdout identity changed")
    require(evaluation["prompt_artifact_sha256"] == expected_evaluation["prompt_sha256"], "prompt artifact identity changed")
    require(evaluation["required_task_levels"] == expected_evaluation["counts"], "wrong holdout composition")
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
        "exploratory inference generation settings changed",
    )


def verify_training_artifact(config: dict[str, Any]) -> dict[str, Any]:
    source = config["source_training"]
    root = Path(source["directory"])
    manifest_path = root / "training-manifest.json"
    summary_path = root / "training-summary.json"
    best_path = root / "best-checkpoint.json"
    for path in (manifest_path, summary_path, best_path):
        require(path.is_file(), f"missing exploratory training artifact: {path.name}")
    require(sha256_file(manifest_path) == source["manifest_sha256"], "exploratory training manifest hash mismatch")
    require(sha256_file(summary_path) == source["summary_sha256"], "exploratory training summary hash mismatch")
    require(sha256_file(best_path) == source["best_checkpoint_sha256"], "exploratory best checkpoint hash mismatch")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    best = json.loads(best_path.read_text(encoding="utf-8"))
    require(manifest["git_commit"] == source["git_commit"], "exploratory training commit mismatch")
    require(manifest["config_sha256"] == source["config_sha256"], "exploratory training config mismatch")
    require(
        manifest["dataset_manifest_sha256"] == source["selection_manifest_sha256"],
        "exploratory selection manifest mismatch",
    )
    require(manifest["adapter_sha256"] == source["adapter_sha256"], "exploratory manifest adapter mismatch")
    require(summary["version"] == TRAINING_VERSION, "wrong exploratory training summary version")
    require(summary["status"] == "completed", "exploratory training did not complete")
    require(summary["optimizer_steps"] == 98, "wrong exploratory optimizer-step count")
    require(summary["train_examples"] == 780, "wrong exploratory train count")
    require(summary["validation_examples"] == 131, "wrong exploratory validation count")
    require(summary["reference_validation_examples"] == 500, "wrong reference validation count")
    require(summary["best_adapter_sha256"] == source["adapter_sha256"], "exploratory summary adapter mismatch")
    require(
        summary["source_adapter_sha256"] == source["source_adapter_sha256"],
        "exploratory source adapter mismatch",
    )
    require(best["checkpoint"] == source["checkpoint"], "exploratory best checkpoint path mismatch")
    require(best["optimizer_step"] == 98 and best["epoch"] == 1, "wrong exploratory best checkpoint step")

    checkpoint = Path(source["checkpoint"])
    require(not checkpoint.is_absolute() and ".." not in checkpoint.parts, "unsafe checkpoint path")
    adapter_dir = root / checkpoint / "adapter"
    weights = adapter_dir / "adapter_model.safetensors"
    require(weights.is_file(), "exploratory adapter weights missing")
    require(sha256_file(weights) == source["adapter_sha256"], "exploratory adapter weights hash mismatch")
    require((adapter_dir / "adapter_config.json").is_file(), "exploratory adapter config missing")
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
