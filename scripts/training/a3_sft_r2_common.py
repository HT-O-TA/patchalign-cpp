"""Fail-closed validation shared by A3.4/SFT-R2 preflight and training."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.training.a3_formal_common import (
    LORA_TARGETS,
    load_jsonl,
    require,
    sha256_file,
)


CONFIG_VERSION = "a3-sft-r2-v1"
DATA_VERSION = "a3-sft-r2-data-v1"
SELECTION_VERSION = "a3-sft-r2-data-v1"


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == CONFIG_VERSION, "wrong R2 config version")
    require(config.get("seed") == 20260830, "wrong R2 seed")
    require(config["model"]["model_id"] == "Qwen/Qwen2.5-Coder-7B", "wrong model id")
    require(
        config["model"]["revision"]
        == "0396a76181e127dfc13e5c5ec48a8cee09938b02",
        "wrong model revision",
    )
    initialization = config["initialization"]
    require(initialization["kind"] == "adapter_continuation", "wrong initialization")
    require(initialization["source_run_id"] == "a33_sft_nf4_s20260830", "wrong source run")
    require(initialization["adapter_sha256"].startswith("sha256:"), "adapter hash missing")
    require(
        config["data"]["expected_counts"] == {"train": 1200, "validation": 117},
        "wrong R2 data counts",
    )
    require(config["data"]["reference_validation_count"] == 500, "wrong reference validation count")
    training = config["training"]
    require(
        {key: training[key] for key in (
            "mode", "epochs", "max_sequence_tokens", "micro_batch_size",
            "gradient_accumulation_steps", "learning_rate", "warmup_steps",
            "weight_decay", "max_grad_norm", "gradient_checkpointing",
            "reset_optimizer_state", "checkpoint_every_optimizer_steps",
            "validation_policy", "reference_validation_policy",
            "best_checkpoint_rule",
        )}
        == {
            "mode": "nf4_qlora_adapter_continuation",
            "epochs": 1,
            "max_sequence_tokens": 4096,
            "micro_batch_size": 1,
            "gradient_accumulation_steps": 8,
            "learning_rate": 0.00002,
            "warmup_steps": 20,
            "weight_decay": 0.0,
            "max_grad_norm": 1.0,
            "gradient_checkpointing": True,
            "reset_optimizer_state": True,
            "checkpoint_every_optimizer_steps": 50,
            "validation_policy": "focused_validation_at_epoch_end",
            "reference_validation_policy": "report_only_before_and_after",
            "best_checkpoint_rule": "lowest_finite_focused_validation_loss_then_earliest_step",
        },
        "R2 training settings changed",
    )
    require(
        training["lora"] == {
            "r": 8,
            "alpha": 16,
            "dropout": 0.0,
            "bias": "none",
            "target_modules": LORA_TARGETS,
        },
        "R2 LoRA settings changed",
    )
    expected_steps = math.ceil(
        config["data"]["expected_counts"]["train"]
        / training["gradient_accumulation_steps"]
    ) * training["epochs"]
    require(expected_steps == 150, "wrong R2 optimizer-step denominator")
    evaluation = config["evaluation"]
    require(evaluation["required_task_levels"] == {"function": 400, "file_window": 100}, "wrong holdout counts")
    require(evaluation["prompt_version"] == "a3-cpp-repair-v1", "wrong prompt version")
    require(evaluation["input_mode"] == "raw_completion", "wrong input mode")
    require(evaluation["allowed_path"] == "main.cpp", "wrong allowed path")
    require(evaluation["scoring_protocol"] == "a3-scoring-v2", "wrong scoring protocol")
    require(
        evaluation["generation"] == {
            "do_sample": False,
            "temperature": None,
            "top_p": None,
            "num_return_sequences": 1,
            "max_input_tokens": 4096,
            "max_new_tokens": 512,
        },
        "R2 generation settings changed",
    )
    require(config["comparison"]["fixed_denominator"] == 500, "wrong comparison denominator")
    require(config["comparison"]["new_confirmation_set_required"] is True, "confirmation set requirement removed")
    require(config["comparison"]["defects4c_minimum_required"] == 150, "wrong external minimum")


def verify_data(
    repo: Path, config_path: Path, config: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    data = config["data"]
    selection_config = repo / data["selection_config"]
    require(selection_config.is_file(), "R2 selection config missing")
    require(sha256_file(selection_config) == data["selection_config_sha256"], "R2 selection config hash mismatch")
    selection_config_value = json.loads(selection_config.read_text(encoding="utf-8"))
    require(selection_config_value["version"] == DATA_VERSION, "wrong R2 selection config version")

    root = Path(data["root"])
    manifest_path = root / data["selection_manifest"]
    require(manifest_path.is_file(), "R2 selection manifest missing")
    require(sha256_file(manifest_path) == data["selection_manifest_sha256"], "R2 selection manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["version"] == SELECTION_VERSION, "wrong selection manifest version")
    require(manifest["config_sha256"] == data["selection_config_sha256"], "selection config/manifest mismatch")
    require(manifest["counts"] == data["expected_counts"], "selection manifest count mismatch")
    require(manifest["data_files"] == data["file_sha256"], "selection manifest file hash mismatch")
    require(
        manifest["isolation"] == {
            "source_is_frozen_a3_sft_only": True,
            "source_and_task_scope": "RunBugRun/function",
            "formal_holdout_content_read": False,
            "hidden_test_content_read": False,
            "train_validation_sample_overlap": 0,
        },
        "selection isolation contract changed",
    )

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    records: dict[str, list[dict[str, Any]]] = {}
    ids: dict[str, set[str]] = {}
    families: dict[str, set[str]] = {}
    for split in ("train", "validation"):
        path = root / f"{split}.jsonl"
        require(path.is_file(), f"R2 {split} file missing")
        require(sha256_file(path) == data["file_sha256"][f"{split}.jsonl"], f"R2 {split} hash mismatch")
        values = load_jsonl(path)
        require(len(values) == data["expected_counts"][split], f"R2 {split} count mismatch")
        ids[split] = set()
        families[split] = set()
        for record in values:
            validator.validate(record)
            sample_id = record["sample_id"]
            require(sample_id not in ids[split], f"duplicate R2 sample: {sample_id}")
            ids[split].add(sample_id)
            families[split].add(record["repo_family"])
            require(record["split"] == split, f"wrong R2 split: {sample_id}")
            require(record["source_dataset"] == "RunBugRun", f"wrong R2 source: {sample_id}")
            require(record["task_level"] == "function", f"wrong R2 task level: {sample_id}")
            require(record["hidden_test_command"] is None, f"hidden test leaked: {sample_id}")
            require(sample_id in manifest["selected_sample_tags"], f"missing safety tags: {sample_id}")
        records[split] = values
        require(
            Counter(record["source_dataset"] for record in values) == {"RunBugRun": len(values)},
            f"wrong R2 {split} source composition",
        )
    require(ids["train"].isdisjoint(ids["validation"]), "R2 train/validation sample overlap")
    require(families["train"].isdisjoint(families["validation"]), "R2 train/validation family overlap")
    require(set(manifest["selected_sample_tags"]) == ids["train"] | ids["validation"], "orphan safety tags")
    return records, manifest


def verify_initial_adapter(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    initialization = config["initialization"]
    adapter = Path(initialization["source_checkpoint"])
    weights = adapter / "adapter_model.safetensors"
    adapter_config_path = adapter / "adapter_config.json"
    require(weights.is_file(), "source M1 adapter weights missing")
    require(adapter_config_path.is_file(), "source M1 adapter config missing")
    require(sha256_file(weights) == initialization["adapter_sha256"], "source M1 adapter hash mismatch")
    require(sha256_file(adapter_config_path) == initialization["adapter_config_sha256"], "source M1 adapter config hash mismatch")
    source_manifest_path = Path(initialization["source_training_manifest"])
    require(source_manifest_path.is_file(), "source M1 training manifest missing")
    require(
        sha256_file(source_manifest_path) == initialization["source_training_manifest_sha256"],
        "source M1 training manifest hash mismatch",
    )
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    require(source_manifest["run_id"] == initialization["source_run_id"], "source M1 run mismatch")
    require(source_manifest["adapter_sha256"] == initialization["adapter_sha256"], "source M1 manifest adapter mismatch")
    adapter_config = json.loads(adapter_config_path.read_text(encoding="utf-8"))
    lora = config["training"]["lora"]
    require(adapter_config["peft_type"] == "LORA", "source adapter is not LoRA")
    require(adapter_config["task_type"] == "CAUSAL_LM", "source adapter task mismatch")
    require(adapter_config["r"] == lora["r"], "source adapter rank mismatch")
    require(adapter_config["lora_alpha"] == lora["alpha"], "source adapter alpha mismatch")
    require(adapter_config["lora_dropout"] == lora["dropout"], "source adapter dropout mismatch")
    require(adapter_config["bias"] == lora["bias"], "source adapter bias mismatch")
    require(set(adapter_config["target_modules"]) == set(lora["target_modules"]), "source adapter targets mismatch")
    return adapter, source_manifest
