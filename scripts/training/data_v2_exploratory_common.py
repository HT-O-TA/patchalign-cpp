"""Fail-closed validation for the Data-v2 exploratory replay continuation."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.data.build_a3_formal_sft_data import payload_key_from_sample
from scripts.training.a3_formal_common import LORA_TARGETS, load_jsonl, require, sha256_file


CONFIG_VERSION = "data-v2-exploratory-replay-training-v0.1"
DATA_VERSION = "data-v2-exploratory-replay-v0.1"


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == CONFIG_VERSION, "wrong Data-v2 exploratory training version")
    require(config.get("seed") == 20260906, "wrong exploratory seed")
    require(config["scope"] == {
        "exploratory_only": True,
        "satisfies_data_v2_1_capacity_contract": False,
        "a5_dpo_started": False,
        "promotion_authorized_before_full_evaluation": False,
    }, "exploratory scope changed")
    model = config["model"]
    require(model["model_id"] == "Qwen/Qwen2.5-Coder-7B", "wrong model ID")
    require(model["revision"] == "0396a76181e127dfc13e5c5ec48a8cee09938b02", "wrong model revision")
    initialization = config["initialization"]
    require(initialization["kind"] == "adapter_continuation", "wrong initialization")
    require(initialization["source_run_id"] == "a34_sft_r2_nf4_s20260830", "wrong source run")
    require(initialization["adapter_sha256"] == "sha256:8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a", "wrong M1-R2 adapter")
    data = config["data"]
    require(data["expected_counts"] == {"train": 780, "validation": 131}, "wrong data counts")
    require(data["expected_task_levels"] == {"train": {"function": 416, "file_window": 364}, "validation": {"function": 74, "file_window": 57}}, "wrong task-level composition")
    require(data["expected_roles"] == {"train": {"formal_train_replay": 520, "safe_increment": 260}, "validation": {"safe_increment": 131}}, "wrong replay roles")
    require(data["reference_validation_count"] == 500, "wrong reference validation count")
    training = config["training"]
    require({key: training[key] for key in (
        "mode", "epochs", "max_sequence_tokens", "micro_batch_size",
        "gradient_accumulation_steps", "learning_rate", "warmup_steps",
        "weight_decay", "max_grad_norm", "gradient_checkpointing",
        "reset_optimizer_state", "checkpoint_every_optimizer_steps",
        "validation_policy", "reference_validation_policy", "best_checkpoint_rule",
    )} == {
        "mode": "nf4_qlora_adapter_continuation",
        "epochs": 1,
        "max_sequence_tokens": 4096,
        "micro_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "learning_rate": 0.00001,
        "warmup_steps": 10,
        "weight_decay": 0.0,
        "max_grad_norm": 1.0,
        "gradient_checkpointing": True,
        "reset_optimizer_state": True,
        "checkpoint_every_optimizer_steps": 49,
        "validation_policy": "focused_validation_at_epoch_end",
        "reference_validation_policy": "report_only_before_and_after",
        "best_checkpoint_rule": "lowest_finite_focused_validation_loss_then_earliest_step",
    }, "training settings changed")
    require(training["lora"] == {
        "r": 8,
        "alpha": 16,
        "dropout": 0.0,
        "bias": "none",
        "target_modules": LORA_TARGETS,
    }, "LoRA settings changed")
    steps = math.ceil(data["expected_counts"]["train"] / training["gradient_accumulation_steps"])
    require(steps == 98, "wrong optimizer-step denominator")
    evaluation = config["evaluation"]
    require(evaluation["required_task_levels"] == {"function": 400, "file_window": 100}, "wrong holdout composition")
    require(evaluation["prompt_version"] == "a3-cpp-repair-v1", "wrong prompt version")
    require(evaluation["input_mode"] == "raw_completion", "wrong input mode")
    require(evaluation["allowed_path"] == "main.cpp", "wrong allowed path")
    require(evaluation["scoring_protocol"] == "a3-scoring-v2", "wrong scoring protocol")
    require(evaluation["generation"] == {
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "num_return_sequences": 1,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
    }, "generation settings changed")
    require(config["preregistered_evaluation"] == {
        "promotion_requires_separate_owner_decision": True,
        "formal_500": {"minimum_pass": 14, "maximum_timeout": 2},
        "confirmation_124": {"minimum_pass": 1, "maximum_timeout": 4, "maximum_regression_failure": 3},
        "defects4c_176": {"minimum_pass": 1, "maximum_timeout": 0},
    }, "preregistered evaluation gates changed")


def verify_data(repo: Path, config: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    data = config["data"]
    root = Path(data["root"])
    manifest_path = root / data["selection_manifest"]
    require(manifest_path.is_file(), "selection manifest missing")
    require(sha256_file(manifest_path) == data["selection_manifest_sha256"], "selection manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["version"] == DATA_VERSION, "wrong data manifest version")
    require(manifest["config_sha256"] == data["selection_config_sha256"], "data config/manifest mismatch")
    require(manifest["counts"] == data["expected_counts"], "manifest counts changed")
    require(manifest["task_level_counts"] == data["expected_task_levels"], "manifest task levels changed")
    require(manifest["roles"] == data["expected_roles"], "manifest replay roles changed")
    require(manifest["data_files"] == data["file_sha256"], "manifest file hashes changed")
    require(manifest["isolation"] == {
        "sample_overlap": 0,
        "payload_overlap": 0,
        "repo_family_overlap": 0,
        "formal_holdout_content_read": False,
        "confirmation_content_read": False,
        "external_content_read": False,
        "evaluation_gold_consumed": False,
    }, "data isolation changed")
    require(manifest["interpretation"]["satisfies_data_v2_1_capacity_contract"] is False, "capacity failure hidden")

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    records: dict[str, list[dict[str, Any]]] = {}
    ids: dict[str, set[str]] = {}
    families: dict[str, set[str]] = {}
    payloads: dict[str, set[str]] = {}
    for split in ("train", "validation"):
        path = root / f"{split}.jsonl"
        require(path.is_file(), f"missing data file: {split}")
        require(sha256_file(path) == data["file_sha256"][f"{split}.jsonl"], f"{split} data changed")
        values = load_jsonl(path)
        require(len(values) == data["expected_counts"][split], f"{split} count changed")
        for record in values:
            validator.validate(record)
            require(record["split"] == split, f"wrong split: {record['sample_id']}")
            require(record["hidden_test_command"] is None, f"hidden test leaked: {record['sample_id']}")
        ids[split] = {row["sample_id"] for row in values}
        families[split] = {row["repo_family"] for row in values}
        payloads[split] = {payload_key_from_sample(row) for row in values}
        require(len(ids[split]) == len(values), f"duplicate {split} IDs")
        require(len(payloads[split]) == len(values), f"duplicate {split} payloads")
        require(dict(sorted(Counter(row["task_level"] for row in values).items())) == data["expected_task_levels"][split], f"{split} task levels changed")
        records[split] = values
    require(ids["train"].isdisjoint(ids["validation"]), "sample overlap")
    require(families["train"].isdisjoint(families["validation"]), "family overlap")
    require(payloads["train"].isdisjoint(payloads["validation"]), "payload overlap")
    return records, manifest


def verify_initial_adapter(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    initialization = config["initialization"]
    adapter = Path(initialization["source_checkpoint"])
    weights = adapter / "adapter_model.safetensors"
    adapter_config_path = adapter / "adapter_config.json"
    require(sha256_file(weights) == initialization["adapter_sha256"], "source adapter changed")
    require(sha256_file(adapter_config_path) == initialization["adapter_config_sha256"], "adapter config changed")
    source_manifest_path = Path(initialization["source_training_manifest"])
    source_summary_path = Path(initialization["source_training_summary"])
    require(sha256_file(source_manifest_path) == initialization["source_training_manifest_sha256"], "source manifest changed")
    require(sha256_file(source_summary_path) == initialization["source_training_summary_sha256"], "source summary changed")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    require(source_manifest["run_id"] == initialization["source_run_id"], "source run mismatch")
    require(source_manifest["adapter_sha256"] == initialization["adapter_sha256"], "source adapter identity mismatch")
    adapter_config = json.loads(adapter_config_path.read_text(encoding="utf-8"))
    lora = config["training"]["lora"]
    require(adapter_config["peft_type"] == "LORA" and adapter_config["task_type"] == "CAUSAL_LM", "source adapter type changed")
    require(adapter_config["r"] == lora["r"], "adapter rank changed")
    require(adapter_config["lora_alpha"] == lora["alpha"], "adapter alpha changed")
    require(adapter_config["lora_dropout"] == lora["dropout"], "adapter dropout changed")
    require(adapter_config["bias"] == lora["bias"], "adapter bias changed")
    require(set(adapter_config["target_modules"]) == set(lora["target_modules"]), "adapter targets changed")
    return adapter, source_manifest
