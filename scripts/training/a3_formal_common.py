"""Shared validation for A3.3 formal training and inference."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any


LORA_TARGETS = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == "a3-sft-formal-v1", "wrong formal config version")
    require(config.get("seed") == 20260830, "wrong formal seed")
    require(config["model"]["model_id"] == "Qwen/Qwen2.5-Coder-7B", "wrong model id")
    require(
        config["model"]["revision"] == "0396a76181e127dfc13e5c5ec48a8cee09938b02",
        "wrong model revision",
    )
    require(config["data"]["expected_counts"] == {"train": 5000, "validation": 500}, "wrong data counts")
    require(
        config["data"]["expected_task_levels"]
        == {
            "train": {"function": 4213, "file_window": 787},
            "validation": {"function": 425, "file_window": 75},
        },
        "wrong task-level counts",
    )
    require(
        config["data"]["expected_sources"]
        == {
            "train": {"CommitPackFT": 2044, "RunBugRun": 2956},
            "validation": {"CommitPackFT": 200, "RunBugRun": 300},
        },
        "wrong source counts",
    )
    training = config["training"]
    require(
        {key: training[key] for key in (
            "mode", "epochs", "max_sequence_tokens", "micro_batch_size",
            "gradient_accumulation_steps", "learning_rate", "warmup_steps",
            "weight_decay", "max_grad_norm", "gradient_checkpointing",
            "checkpoint_every_optimizer_steps", "validation_policy",
            "best_checkpoint_rule",
        )}
        == {
            "mode": "nf4_qlora",
            "epochs": 3,
            "max_sequence_tokens": 4096,
            "micro_batch_size": 1,
            "gradient_accumulation_steps": 8,
            "learning_rate": 0.0001,
            "warmup_steps": 50,
            "weight_decay": 0.0,
            "max_grad_norm": 1.0,
            "gradient_checkpointing": True,
            "checkpoint_every_optimizer_steps": 200,
            "validation_policy": "full_validation_at_epoch_end",
            "best_checkpoint_rule": "lowest_finite_validation_loss_then_earliest_step",
        },
        "formal training settings changed",
    )
    require(
        training["lora"]
        == {
            "r": 8, "alpha": 16, "dropout": 0.0, "bias": "none",
            "target_modules": LORA_TARGETS,
        },
        "formal LoRA settings changed",
    )
    evaluation = config["evaluation"]
    require(evaluation["required_task_levels"] == {"function": 400, "file_window": 100}, "wrong holdout counts")
    require(evaluation["scoring_protocol"] == "a3-scoring-v2", "wrong scoring protocol")
    require(evaluation["prompt_version"] == "a3-cpp-repair-v1", "wrong prompt version")
    require(evaluation["allowed_path"] == "main.cpp", "wrong allowed path")
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
        "generation settings changed",
    )


def verify_lock(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    data_root = Path(config["data"]["root"])
    lock_path = data_root / config["data"]["freeze_lock"]
    require(lock_path.is_file(), f"missing data freeze lock: {lock_path}")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    require(lock["version"] == "a3-formal-data-lock-v1", "wrong data lock version")
    require(lock["config_sha256"] == sha256_file(config_path), "config/lock hash mismatch")
    require(lock["counts"] == config["data"]["expected_counts"], "lock count mismatch")
    require(lock["task_level_counts"] == config["data"]["expected_task_levels"], "lock task mismatch")
    require(lock["source_counts"] == config["data"]["expected_sources"], "lock source mismatch")
    require(
        lock["isolation"]
        == {"train_validation_family_overlap": 0, "sft_holdout_problem_overlap": 0},
        "lock isolation mismatch",
    )
    for name, expected in lock["data_files"].items():
        require(sha256_file(data_root / name) == expected, f"data hash mismatch: {name}")
    holdout_root = Path(config["evaluation"]["holdout_root"])
    for name, expected in lock["holdout_files"].items():
        require(sha256_file(holdout_root / name) == expected, f"holdout hash mismatch: {name}")
    return lock


def verify_records(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    data_root = Path(config["data"]["root"])
    records = {
        split: load_jsonl(data_root / f"{split}.jsonl")
        for split in ("train", "validation")
    }
    for split, values in records.items():
        require(len(values) == config["data"]["expected_counts"][split], f"{split} count mismatch")
        require(
            dict(Counter(x["task_level"] for x in values))
            == config["data"]["expected_task_levels"][split],
            f"{split} task composition mismatch",
        )
        require(
            dict(Counter(x["source_dataset"] for x in values))
            == config["data"]["expected_sources"][split],
            f"{split} source composition mismatch",
        )
    return records
