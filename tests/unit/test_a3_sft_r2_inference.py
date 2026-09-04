from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.training.a3_formal_common import sha256_file, write_json
from scripts.training.a3_sft_r2_inference_common import (
    validate_config,
    verify_holdout_manifest,
    verify_training_artifact,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/evaluation/a3_sft_r2_inference_v1.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_r2_inference_contract_is_frozen() -> None:
    config = load_config()
    validate_config(config)
    assert config["evaluation"]["required_task_levels"] == {
        "function": 400,
        "file_window": 100,
    }
    assert config["evaluation"]["generation"]["max_new_tokens"] == 512
    assert config["source_training"]["git_commit"] == (
        "8e8505cd457aff7b8397bb78c4fe04e4ac3bf68c"
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("run_id",), "changed"),
        (("source_training", "checkpoint"), "checkpoints/other"),
        (("evaluation", "input_mode"), "chat_template"),
        (("evaluation", "prompt_artifact_sha256"), "sha256:" + "0" * 64),
        (("evaluation", "required_task_levels", "function"), 399),
        (("evaluation", "generation", "max_new_tokens"), 1024),
    ],
)
def test_r2_inference_contract_rejects_drift(
    path: tuple[str, ...], value: object
) -> None:
    config = load_config()
    changed = copy.deepcopy(config)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)


def make_training_artifact(tmp_path: Path) -> dict:
    config = load_config()
    source = config["source_training"]
    source["directory"] = str(tmp_path)
    adapter_dir = tmp_path / source["checkpoint"] / "adapter"
    adapter_dir.mkdir(parents=True)
    weights = adapter_dir / "adapter_model.safetensors"
    weights.write_bytes(b"frozen-r2-adapter")
    (adapter_dir / "adapter_config.json").write_text("{}\n", encoding="utf-8")
    source["adapter_sha256"] = sha256_file(weights)

    manifest = {
        "git_commit": source["git_commit"],
        "config_sha256": source["config_sha256"],
        "dataset_manifest_sha256": source["selection_manifest_sha256"],
        "adapter_sha256": source["adapter_sha256"],
    }
    summary = {
        "version": "a3-sft-r2-training-v1",
        "status": "completed",
        "optimizer_steps": 150,
        "train_examples": 1200,
        "validation_examples": 117,
        "reference_validation_examples": 500,
        "best_adapter_sha256": source["adapter_sha256"],
        "source_adapter_sha256": source["source_adapter_sha256"],
    }
    best = {
        "checkpoint": source["checkpoint"],
        "optimizer_step": 150,
        "epoch": 1,
    }
    write_json(tmp_path / "training-manifest.json", manifest)
    write_json(tmp_path / "training-summary.json", summary)
    write_json(tmp_path / "best-checkpoint.json", best)
    source["manifest_sha256"] = sha256_file(tmp_path / "training-manifest.json")
    source["summary_sha256"] = sha256_file(tmp_path / "training-summary.json")
    source["best_checkpoint_sha256"] = sha256_file(tmp_path / "best-checkpoint.json")
    return config


def test_training_artifact_binding_detects_adapter_tampering(tmp_path: Path) -> None:
    config = make_training_artifact(tmp_path)
    result = verify_training_artifact(config)
    assert result["adapter_dir"].name == "adapter"
    weights = result["adapter_dir"] / "adapter_model.safetensors"
    weights.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="adapter weights hash mismatch"):
        verify_training_artifact(config)


def test_holdout_manifest_binding_detects_tampering(tmp_path: Path) -> None:
    config = load_config()
    manifest = tmp_path / "a2-manifest.json"
    manifest.write_text('{"version": "test"}\n', encoding="utf-8")
    config["evaluation"]["holdout_root"] = str(tmp_path)
    config["evaluation"]["holdout_manifest_sha256"] = sha256_file(manifest)
    assert verify_holdout_manifest(config) == manifest
    manifest.write_text('{"version": "changed"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="holdout manifest hash mismatch"):
        verify_holdout_manifest(config)
