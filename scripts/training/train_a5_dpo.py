#!/usr/bin/env python3
"""Run the frozen A5 DPO GPU smoke or one reportable beta variant."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
import math
import os
from pathlib import Path
import random
import subprocess
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.a5_dpo_common import (
    dpo_rows,
    read_json,
    validate_config,
    variant,
    verify_frozen_inputs,
)


SMOKE_VERSION = "a5-dpo-gpu-smoke-v1.1"
TRAINING_VERSION = "a5-dpo-training-v1.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def verify_cpu_preflight(path: Path, config_path: Path, config: dict[str, Any], commit: str) -> dict[str, Any]:
    require(path.is_file(), "A5 DPO CPU preflight missing")
    report = read_json(path)
    require(report["version"] == "a5-dpo-cpu-preflight-v1.1", "wrong CPU preflight version")
    require(report["status"] == "passed", "CPU preflight did not pass")
    require(report["git_commit"] == commit, "CPU preflight commit mismatch")
    require(report["config_sha256"] == sha256_file(config_path), "CPU preflight config mismatch")
    require(report["environment_sha256"] == config["environment"]["lock_sha256"], "CPU preflight environment mismatch")
    require(report["preferences_sha256"] == config["data"]["preferences_sha256"], "CPU preflight data mismatch")
    require(report["pair_count"] == config["data"]["expected_pairs"], "CPU preflight pair count mismatch")
    require(report["truncated_rows"] == 0, "CPU preflight found truncation")
    return report


def verify_gpu_smoke(path: Path, config_path: Path, config: dict[str, Any], commit: str, cpu_preflight: Path) -> dict[str, Any]:
    require(path.is_file(), "A5 DPO GPU smoke report missing")
    report = read_json(path)
    require(report["version"] == SMOKE_VERSION, "wrong GPU smoke version")
    require(report["status"] == "passed", "GPU smoke did not pass")
    require(report["git_commit"] == commit, "GPU smoke commit mismatch")
    require(report["config_sha256"] == sha256_file(config_path), "GPU smoke config mismatch")
    require(report["cpu_preflight_sha256"] == sha256_file(cpu_preflight), "GPU smoke CPU-preflight mismatch")
    require(report["source_adapter_sha256"] == config["initialization"]["adapter_sha256"], "GPU smoke adapter mismatch")
    require(report["optimizer_steps"] == 1, "GPU smoke did not complete exactly one step")
    return report


def load_models(config: dict[str, Any], torch: Any) -> tuple[Any, Any, int, int]:
    from peft import PeftModel, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    common = {
        "pretrained_model_name_or_path": config["model"]["local_path"],
        "local_files_only": True,
        "trust_remote_code": False,
        "low_cpu_mem_usage": True,
        "device_map": {"": 0},
        "dtype": torch.bfloat16,
        "quantization_config": quantization,
    }
    policy_base = AutoModelForCausalLM.from_pretrained(**common)
    policy_base = prepare_model_for_kbit_training(
        policy_base,
        use_gradient_checkpointing=config["training"]["gradient_checkpointing"],
        gradient_checkpointing_kwargs={
            "use_reentrant": config["training"]["gradient_checkpointing_use_reentrant"]
        },
    )
    policy = PeftModel.from_pretrained(
        policy_base, config["initialization"]["adapter_path"], is_trainable=True,
    )
    policy.config.use_cache = False
    trainable = sum(parameter.numel() for parameter in policy.parameters() if parameter.requires_grad)
    total = sum(parameter.numel() for parameter in policy.parameters())
    require(trainable > 0, "DPO policy has no trainable parameters")

    reference_base = AutoModelForCausalLM.from_pretrained(**common)
    reference = PeftModel.from_pretrained(
        reference_base, config["initialization"]["adapter_path"], is_trainable=False,
    )
    reference.config.use_cache = False
    reference.eval()
    require(not any(parameter.requires_grad for parameter in reference.parameters()), "DPO reference is trainable")
    return policy, reference, trainable, total


def build_training_args(config: dict[str, Any], choice: dict[str, Any], output: Path, smoke: bool) -> Any:
    from trl import DPOConfig

    training = config["training"]
    return DPOConfig(
        output_dir=str(output),
        overwrite_output_dir=False,
        do_train=True,
        per_device_train_batch_size=training["micro_batch_size"],
        gradient_accumulation_steps=1 if smoke else training["gradient_accumulation_steps"],
        learning_rate=training["learning_rate"],
        weight_decay=training["weight_decay"],
        max_grad_norm=training["max_grad_norm"],
        num_train_epochs=1 if smoke else training["epochs"],
        max_steps=1 if smoke else -1,
        lr_scheduler_type=training["lr_scheduler_type"],
        warmup_steps=0 if smoke else training["warmup_steps"],
        logging_strategy="steps",
        logging_first_step=True,
        logging_steps=training["logging_steps"],
        save_strategy="no" if smoke else training["save_strategy"],
        save_total_limit=training["save_total_limit"],
        save_only_model=True,
        seed=config["seed"],
        data_seed=config["seed"],
        bf16=True,
        fp16=False,
        tf32=False,
        gradient_checkpointing=training["gradient_checkpointing"],
        gradient_checkpointing_kwargs={
            "use_reentrant": training["gradient_checkpointing_use_reentrant"]
        },
        dataloader_num_workers=0,
        report_to="none",
        optim=training["optimizer"],
        disable_dropout=training["disable_dropout"],
        max_prompt_length=training["max_prompt_tokens"],
        max_completion_length=training["max_completion_tokens"],
        max_length=training["max_sequence_tokens"],
        truncation_mode=training["truncation_mode"],
        loss_type=training["loss_type"],
        beta=choice["beta"],
        reference_free=training["reference_free"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cpu-preflight", type=Path, required=True)
    parser.add_argument("--gpu-smoke", type=Path)
    parser.add_argument("--variant", choices=("beta01", "beta03"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-report", type=Path)
    args = parser.parse_args()
    smoke = args.smoke_report is not None

    os.environ.setdefault("PYTHONNOUSERSITE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(config)
    pairs = verify_frozen_inputs(config, repo)
    choice = variant(config, args.variant)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "DPO training requires a clean worktree")
    cpu_report = verify_cpu_preflight(args.cpu_preflight, args.config, config, commit)

    expected_output = (
        Path(config["outputs"]["preflight_directory"]) / "gpu-smoke-work"
        if smoke else Path(config["outputs"]["training_root"]) / args.variant
    )
    require(args.output_dir == expected_output, "unexpected DPO output directory")
    require(not args.output_dir.exists(), "refusing to overwrite DPO output")
    if smoke:
        require(args.variant == "beta01", "GPU smoke must use main beta")
        require(args.smoke_report == Path(config["outputs"]["gpu_smoke"]), "unexpected GPU smoke report")
        require(not args.smoke_report.exists(), "refusing to overwrite GPU smoke report")
        longest = cpu_report["longest_pair_id"]
        selected = [row for row in pairs if row["pair_id"] == longest]
        require(len(selected) == 1, "longest smoke pair missing")
        pairs = selected
    else:
        require(args.gpu_smoke is not None, "formal DPO requires GPU smoke")
        verify_gpu_smoke(args.gpu_smoke, args.config, config, commit, args.cpu_preflight)

    import numpy as np
    import torch
    from datasets import Dataset
    from transformers import AutoTokenizer
    from trl import DPOTrainer

    require(torch.cuda.is_available(), "CUDA unavailable")
    require(torch.cuda.device_count() == 1, "exactly one visible GPU required")
    require(torch.cuda.is_bf16_supported(), "BF16 unsupported")
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["local_path"], local_files_only=True,
        trust_remote_code=False, use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    tokenizer.padding_side = "left"
    policy, reference, trainable_parameters, total_parameters = load_models(config, torch)
    training_args = build_training_args(config, choice, args.output_dir, smoke)
    dataset = Dataset.from_list(dpo_rows(pairs))
    trainer = DPOTrainer(
        model=policy,
        ref_model=reference,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    started_at = utc_now()
    result = trainer.train()
    torch.cuda.synchronize()
    peak = int(torch.cuda.max_memory_allocated())
    require(math.isfinite(float(result.metrics["train_loss"])), "non-finite DPO train loss")

    if smoke:
        require(trainer.state.global_step == 1, "GPU smoke step mismatch")
        report = {
            "version": SMOKE_VERSION,
            "status": "passed",
            "started_at": started_at,
            "finished_at": utc_now(),
            "git_commit": commit,
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", "local"),
            "host": os.uname().nodename,
            "gpu": torch.cuda.get_device_name(0),
            "config_sha256": sha256_file(args.config),
            "cpu_preflight_sha256": sha256_file(args.cpu_preflight),
            "source_adapter_sha256": config["initialization"]["adapter_sha256"],
            "variant": choice,
            "pair_id": pairs[0]["pair_id"],
            "optimizer_steps": trainer.state.global_step,
            "train_loss": float(result.metrics["train_loss"]),
            "peak_gpu_memory_bytes": peak,
            "trainable_parameters": trainable_parameters,
            "total_parameters": total_parameters,
        }
        args.smoke_report.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.smoke_report, report)
        print(json.dumps(report, sort_keys=True))
        return

    require(trainer.state.global_step == config["training"]["expected_optimizer_steps"], "DPO optimizer-step mismatch")
    adapter_dir = args.output_dir / "final-adapter"
    policy.save_pretrained(adapter_dir, safe_serialization=True)
    tokenizer.save_pretrained(args.output_dir / "tokenizer")
    trainer.state.save_to_json(str(args.output_dir / "trainer-state.json"))
    weights = adapter_dir / "adapter_model.safetensors"
    adapter_config = adapter_dir / "adapter_config.json"
    require(weights.is_file() and adapter_config.is_file(), "final DPO adapter incomplete")
    summary = {
        "version": TRAINING_VERSION,
        "status": "completed",
        "variant": choice,
        "seed": config["seed"],
        "pairs": len(pairs),
        "epochs": config["training"]["epochs"],
        "optimizer_steps": trainer.state.global_step,
        "train_loss": float(result.metrics["train_loss"]),
        "train_runtime_seconds": float(result.metrics["train_runtime"]),
        "peak_gpu_memory_bytes": peak,
        "trainable_parameters": trainable_parameters,
        "total_parameters": total_parameters,
        "source_adapter_sha256": config["initialization"]["adapter_sha256"],
        "adapter_sha256": sha256_file(weights),
        "adapter_config_sha256": sha256_file(adapter_config),
        "started_at": started_at,
        "finished_at": utc_now(),
    }
    write_json(args.output_dir / "training-summary.json", summary)
    manifest = {
        "schema_version": "0.1.0",
        "run_id": f"a5_dpo_{args.variant}_s{config['seed']}",
        "stage": "dpo",
        "variant": choice,
        "seed": config["seed"],
        "git_commit": commit,
        "dirty_worktree": False,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", "local"),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "model_config_sha256": config["model"]["config_sha256"],
        "source_run_id": config["initialization"]["source_run_id"],
        "source_adapter_sha256": config["initialization"]["adapter_sha256"],
        "preferences_sha256": config["data"]["preferences_sha256"],
        "config_sha256": sha256_file(args.config),
        "environment_sha256": config["environment"]["lock_sha256"],
        "cpu_preflight_sha256": sha256_file(args.cpu_preflight),
        "gpu_smoke_sha256": sha256_file(args.gpu_smoke),
        "adapter_sha256": summary["adapter_sha256"],
        "execution_artifact_sha256": sha256_file(args.output_dir / "training-summary.json"),
        "started_at": started_at,
        "finished_at": utc_now(),
    }
    write_json(args.output_dir / "training-manifest.json", manifest)
    print(json.dumps({
        "status": "completed", "variant": args.variant,
        "optimizer_steps": trainer.state.global_step,
        "adapter_sha256": summary["adapter_sha256"],
        "manifest_sha256": sha256_file(args.output_dir / "training-manifest.json"),
    }, sort_keys=True))
    del trainer, policy, reference
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
