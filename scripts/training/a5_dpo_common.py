"""Frozen validation helpers for resume-delivery A5 DPO."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file


CONFIG_VERSION = "a5-dpo-v1.1"
EXPECTED_PACKAGES = {
    "accelerate": "1.13.0",
    "bitsandbytes": "0.49.2",
    "datasets": "3.6.0",
    "peft": "0.18.1",
    "transformers": "4.57.6",
    "trl": "0.28.0",
}
EXPECTED_VARIANTS = [
    {"name": "beta01", "role": "main", "beta": 0.1},
    {"name": "beta03", "role": "control", "beta": 0.3},
]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == CONFIG_VERSION, "wrong A5 DPO config version")
    require(config.get("seed") == 20260830, "wrong A5 DPO seed")
    require(config["contract"] == {
        "scope_decision": "docs/decisions/0031-resume-delivery-scope.md",
        "scope_decision_sha256": "sha256:4ff1d3f972a0649699a1f5874e8b3c0ca1c097a77eb890303e24971d6443e003",
        "selection_correction": "docs/decisions/0032-dpo-selection-contract-correction.md",
    }, "A5 DPO contract binding changed")
    require(config["model"] == {
        "model_id": "Qwen/Qwen2.5-Coder-7B",
        "local_path": "/mingli01/models/Qwen2.5-Coder-7B",
        "revision": "0396a76181e127dfc13e5c5ec48a8cee09938b02",
        "config_sha256": "sha256:4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605",
    }, "A5 DPO model identity changed")
    require(config["environment"]["packages"] == EXPECTED_PACKAGES, "A5 DPO package versions changed")
    require(config["environment"]["python_no_user_site"] is True, "user-site isolation removed")
    require(config["variants"] == EXPECTED_VARIANTS, "A5 DPO variants changed")
    require(config["data"]["expected_pairs"] == 175, "wrong DPO pair denominator")
    require(config["data"]["expected_chosen_success_pairs"] == 75, "wrong chosen-success denominator")
    require(config["data"]["dev_expected_count"] == 64, "wrong dev denominator")
    require(config["data"]["training_dev_overlap"] == 0, "training/dev isolation changed")
    require(config["training"] == {
        "mode": "nf4_qlora_dpo_adapter_continuation",
        "epochs": 2,
        "micro_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "expected_optimizer_steps": 44,
        "learning_rate": 0.000005,
        "warmup_steps": 4,
        "weight_decay": 0.0,
        "max_grad_norm": 1.0,
        "gradient_checkpointing": True,
        "gradient_checkpointing_use_reentrant": False,
        "max_prompt_tokens": 3072,
        "max_completion_tokens": 640,
        "max_sequence_tokens": 4096,
        "truncation_mode": "keep_end",
        "optimizer": "adamw_torch",
        "lr_scheduler_type": "linear",
        "loss_type": "sigmoid",
        "reference_free": False,
        "disable_dropout": True,
        "save_strategy": "epoch",
        "save_total_limit": 2,
        "logging_steps": 1,
    }, "A5 DPO training recipe changed")
    steps = math.ceil(
        config["data"]["expected_pairs"]
        / config["training"]["gradient_accumulation_steps"]
    ) * config["training"]["epochs"]
    require(steps == config["training"]["expected_optimizer_steps"], "wrong optimizer-step denominator")
    require(config["selection"] == {
        "dataset": "independent-dev-exec-v1",
        "fixed_denominator": 64,
        "baseline": "M1-R2",
        "candidates": ["beta01", "beta03"],
        "priority": [
            "pass_count_desc",
            "hidden_test_success_desc",
            "public_test_success_desc",
            "compile_success_desc",
            "apply_success_desc",
        ],
        "non_degradation_constraints": {
            "timeout_count_not_above_m1_r2": True,
            "regression_failure_count_not_above_m1_r2": True,
        },
        "positive_signal": "strict_lexicographic_improvement_over_m1_r2_on_priority",
        "no_eligible_or_positive_signal_policy": "select_lowest_regression_then_timeout_risk_and_report_negative_result",
        "exact_tie": "beta03_lower_divergence_risk",
        "training_data_used_for_selection": False,
    }, "A5 DPO selection contract changed")


def variant(config: dict[str, Any], name: str) -> dict[str, Any]:
    values = [item for item in config["variants"] if item["name"] == name]
    require(len(values) == 1, f"unknown DPO variant: {name}")
    return values[0]


def verify_frozen_inputs(
    config: dict[str, Any], repo: Path | None = None
) -> list[dict[str, Any]]:
    if repo is not None:
        contract = config["contract"]
        require(
            sha256_file(repo / contract["scope_decision"])
            == contract["scope_decision_sha256"],
            "DPO scope decision changed",
        )
        require(
            (repo / contract["selection_correction"]).is_file(),
            "DPO selection correction missing",
        )
    model_config = Path(config["model"]["local_path"]) / "config.json"
    require(model_config.is_file(), "base model config missing")
    require(sha256_file(model_config) == config["model"]["config_sha256"], "base model config changed")

    initialization = config["initialization"]
    require(initialization["kind"] == "m1_r2_adapter_continuation", "wrong DPO initialization")
    adapter = Path(initialization["adapter_path"])
    weights = adapter / "adapter_model.safetensors"
    adapter_config = adapter / "adapter_config.json"
    require(weights.is_file() and adapter_config.is_file(), "M1-R2 adapter incomplete")
    require(sha256_file(weights) == initialization["adapter_sha256"], "M1-R2 adapter changed")
    require(sha256_file(adapter_config) == initialization["adapter_config_sha256"], "M1-R2 adapter config changed")
    source_manifest_path = Path(initialization["training_manifest"])
    require(sha256_file(source_manifest_path) == initialization["training_manifest_sha256"], "M1-R2 manifest changed")
    source_manifest = read_json(source_manifest_path)
    require(source_manifest["run_id"] == initialization["source_run_id"], "wrong M1-R2 source run")
    require(source_manifest["adapter_sha256"] == initialization["adapter_sha256"], "M1-R2 manifest binding changed")

    data = config["data"]
    preference_path = Path(data["preferences"])
    audit_manifest_path = Path(data["preference_audit_manifest"])
    dev_manifest_path = Path(data["dev_exec_manifest"])
    require(sha256_file(preference_path) == data["preferences_sha256"], "DPO preferences changed")
    require(sha256_file(audit_manifest_path) == data["preference_audit_manifest_sha256"], "preference audit manifest changed")
    require(sha256_file(dev_manifest_path) == data["dev_exec_manifest_sha256"], "dev manifest changed")
    audit_manifest = read_json(audit_manifest_path)
    require(audit_manifest["resume_gate_passed"] is True, "resume preference gate not passed")
    require(audit_manifest["research_gate_300_150_passed"] is False, "research gate history changed")
    require(audit_manifest["approved_pairs"] == data["expected_pairs"], "approved pair count changed")
    require(audit_manifest["chosen_success_pairs"] == data["expected_chosen_success_pairs"], "chosen-success count changed")
    require(audit_manifest["output_sha256"]["preferences.jsonl"] == data["preferences_sha256"], "preference output binding changed")
    require(audit_manifest["input_sha256"]["dev_exec_manifest"] == data["dev_exec_manifest_sha256"], "dev binding changed")
    dev_manifest = read_json(dev_manifest_path)
    require(dev_manifest["selected_count"] == data["dev_expected_count"], "dev count changed")
    require(dev_manifest["a4_selected_overlap"] == data["training_dev_overlap"], "training/dev overlap changed")
    require(dev_manifest["problem_family_unique"] is True, "dev family uniqueness changed")

    environment_lock = Path(config["environment"]["lock"])
    require(environment_lock.is_file(), "environment lock missing")
    require(sha256_file(environment_lock) == config["environment"]["lock_sha256"], "environment lock changed")

    pairs = read_jsonl(preference_path)
    require(len(pairs) == data["expected_pairs"], "DPO preference row count changed")
    require(len({row["pair_id"] for row in pairs}) == len(pairs), "duplicate DPO pair id")
    require(len({row["case_id"] for row in pairs}) == len(pairs), "more than one DPO pair per case")
    require(Counter(row["task_level"] for row in pairs) == {"function": 168, "file_window": 7}, "DPO task mix changed")
    for row in pairs:
        require(row["chosen"]["response"] != row["rejected"]["response"], "identical DPO responses")
    return pairs


def dpo_rows(pairs: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "prompt": row["prompt"],
            "chosen": row["chosen"]["response"],
            "rejected": row["rejected"]["response"],
        }
        for row in pairs
    ]
