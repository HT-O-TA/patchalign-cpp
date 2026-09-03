"""Checkpointed, segmented NF4 QLoRA training for A3.3."""

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
import tempfile
import time
from typing import Any

from scripts.training.a3_formal_common import (
    require,
    sha256_file,
    validate_config,
    verify_lock,
    verify_records,
    write_json,
)
from scripts.training.train_a3_sft_pilot import (
    encode_example,
    load_base_model,
    make_batch,
    sha256_json,
    training_order,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_state(repo: Path) -> tuple[str, bool]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip())
    return commit, dirty


def save_checkpoint(
    output: Path,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    torch: Any,
    state: dict[str, Any],
) -> Path:
    checkpoints = output / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    destination = checkpoints / f"checkpoint-step-{state['completed_steps']:06d}"
    require(not destination.exists(), f"checkpoint already exists: {destination}")
    temporary = Path(tempfile.mkdtemp(prefix=".building-", dir=checkpoints))
    try:
        adapter = temporary / "adapter"
        model.save_pretrained(adapter, safe_serialization=True)
        payload = {
            **state,
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "python_random_state": random.getstate(),
            "torch_random_state": torch.get_rng_state(),
            "cuda_random_state": torch.cuda.get_rng_state_all(),
        }
        torch.save(payload, temporary / "trainer-state.pt")
        write_json(
            temporary / "checkpoint.json",
            {
                key: value
                for key, value in state.items()
                if key not in {"train_loss_sum"}
            },
        )
        temporary.rename(destination)
    except BaseException:
        import shutil
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    write_json(
        checkpoints / "latest.json",
        {
            "checkpoint": str(destination.relative_to(output)),
            "completed_steps": state["completed_steps"],
            "next_epoch": state["next_epoch"],
            "next_offset": state["next_offset"],
        },
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--segment-seconds", type=int, default=27600)
    args = parser.parse_args()
    require(args.segment_seconds >= 600, "segment must allow at least 600 seconds")
    os.environ.setdefault("PYTHONNOUSERSITE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    lock = verify_lock(args.config, config)
    commit, dirty = git_state(repo)
    require(not dirty, "formal training requires a clean worktree")
    require(args.environment_lock.is_file(), "environment lock missing")
    require(
        sha256_file(Path(config["model"]["local_path"]) / "config.json")
        == config["model"]["config_sha256"],
        "model config hash mismatch",
    )
    completed_marker = args.output_dir / "training-manifest.json"
    if completed_marker.exists():
        manifest = json.loads(completed_marker.read_text(encoding="utf-8"))
        require(manifest["git_commit"] == commit, "completed run commit mismatch")
        require(manifest["config_sha256"] == sha256_file(args.config), "completed run config mismatch")
        print(json.dumps({"status": "already_completed", "output": str(args.output_dir)}, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    segment_started = time.monotonic()

    import numpy as np
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoTokenizer, get_linear_schedule_with_warmup

    require(torch.cuda.is_available(), "CUDA unavailable")
    require(torch.cuda.device_count() == 1, "exactly one visible GPU required")
    require(torch.cuda.is_bf16_supported(), "BF16 compute unsupported")
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)

    records = verify_records(config)
    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["local_path"], local_files_only=True,
        trust_remote_code=False, use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    encoded = {
        split: [
            encode_example(tokenizer, item, config["training"]["max_sequence_tokens"])
            for item in values
        ]
        for split, values in records.items()
    }
    orders = training_order(len(encoded["train"]), config["training"]["epochs"], config["seed"])
    accumulation = config["training"]["gradient_accumulation_steps"]
    total_steps = sum(math.ceil(len(order) / accumulation) for order in orders)
    order_ids = [[encoded["train"][index]["sample_id"] for index in order] for order in orders]

    latest_path = args.output_dir / "checkpoints" / "latest.json"
    resume_dir: Path | None = None
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        resume_dir = args.output_dir / latest["checkpoint"]

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    base = load_base_model(
        Path(config["model"]["local_path"]),
        "nf4_qlora",
        config["training"]["gradient_checkpointing"],
    )
    base.config.use_cache = False
    if resume_dir is None:
        lora = config["training"]["lora"]
        model = get_peft_model(
            base,
            LoraConfig(
                task_type="CAUSAL_LM", r=lora["r"], lora_alpha=lora["alpha"],
                lora_dropout=lora["dropout"], bias=lora["bias"],
                target_modules=lora["target_modules"],
            ),
        )
    else:
        model = PeftModel.from_pretrained(
            base, resume_dir / "adapter", is_trainable=True
        )

    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    require(bool(trainable), "no trainable adapter parameters")
    optimizer = torch.optim.AdamW(
        trainable,
        lr=config["training"]["learning_rate"],
        weight_decay=config["training"]["weight_decay"],
    )
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=config["training"]["warmup_steps"],
        num_training_steps=total_steps,
    )
    state: dict[str, Any] = {
        "version": "a3-formal-trainer-state-v1",
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "data_lock_sha256": sha256_file(
            Path(config["data"]["root"]) / config["data"]["freeze_lock"]
        ),
        "next_epoch": 0,
        "next_offset": 0,
        "completed_steps": 0,
        "micro_steps": 0,
        "train_loss_sum": 0.0,
        "best": None,
        "peak_gpu_memory_bytes": 0,
        "started_at": utc_now(),
    }
    if resume_dir is not None:
        loaded = torch.load(resume_dir / "trainer-state.pt", map_location="cuda", weights_only=False)
        for field in ("version", "git_commit", "config_sha256", "data_lock_sha256"):
            require(loaded[field] == state[field], f"resume state mismatch: {field}")
        optimizer.load_state_dict(loaded["optimizer"])
        scheduler.load_state_dict(loaded["scheduler"])
        random.setstate(loaded["python_random_state"])
        torch.set_rng_state(loaded["torch_random_state"].cpu())
        torch.cuda.set_rng_state_all(loaded["cuda_random_state"])
        state = {
            key: value
            for key, value in loaded.items()
            if key not in {"optimizer", "scheduler", "python_random_state", "torch_random_state", "cuda_random_state"}
        }

    checkpoint_every = config["training"]["checkpoint_every_optimizer_steps"]
    last_checkpoint: Path | None = resume_dir
    model.train()
    for epoch_index in range(state["next_epoch"], len(orders)):
        order = orders[epoch_index]
        start_offset = state["next_offset"] if epoch_index == state["next_epoch"] else 0
        for start in range(start_offset, len(order), accumulation):
            group = order[start:start + accumulation]
            optimizer.zero_grad(set_to_none=True)
            losses = []
            for index in group:
                batch = make_batch(torch, encoded["train"][index])
                output = model(**batch)
                loss = output.loss
                require(torch.isfinite(loss).item(), "non-finite training loss")
                (loss / len(group)).backward()
                value = float(loss.detach().float().item())
                losses.append(value)
                state["train_loss_sum"] += value
                state["micro_steps"] += 1
                del output, loss, batch
            grad_norm = torch.nn.utils.clip_grad_norm_(trainable, config["training"]["max_grad_norm"])
            require(torch.isfinite(grad_norm).item(), "non-finite gradient norm")
            optimizer.step()
            scheduler.step()
            state["completed_steps"] += 1
            state["next_epoch"] = epoch_index
            state["next_offset"] = start + len(group)
            state["peak_gpu_memory_bytes"] = max(
                state["peak_gpu_memory_bytes"], int(torch.cuda.max_memory_allocated())
            )
            print(json.dumps({
                "epoch": epoch_index + 1,
                "optimizer_step": state["completed_steps"],
                "optimizer_steps": total_steps,
                "mean_loss": sum(losses) / len(losses),
                "learning_rate": scheduler.get_last_lr()[0],
                "grad_norm": float(grad_norm),
            }, sort_keys=True), flush=True)
            should_checkpoint = state["completed_steps"] % checkpoint_every == 0
            segment_expired = time.monotonic() - segment_started >= args.segment_seconds
            if should_checkpoint or segment_expired:
                last_checkpoint = save_checkpoint(
                    args.output_dir, model, optimizer, scheduler, torch, state
                )
            if segment_expired:
                print(json.dumps({
                    "status": "segment_completed",
                    "checkpoint": str(last_checkpoint),
                    "completed_steps": state["completed_steps"],
                }, sort_keys=True), flush=True)
                return

        model.eval()
        validation_loss_sum = 0.0
        with torch.inference_mode():
            for example in encoded["validation"]:
                batch = make_batch(torch, example)
                loss = model(**batch).loss
                require(torch.isfinite(loss).item(), "non-finite validation loss")
                validation_loss_sum += float(loss.float().item())
                del loss, batch
        validation_loss = validation_loss_sum / len(encoded["validation"])
        state["next_epoch"] = epoch_index + 1
        state["next_offset"] = 0
        candidate = {
            "validation_loss": validation_loss,
            "optimizer_step": state["completed_steps"],
            "epoch": epoch_index + 1,
        }
        if state["best"] is None or (
            candidate["validation_loss"], candidate["optimizer_step"]
        ) < (
            state["best"]["validation_loss"], state["best"]["optimizer_step"]
        ):
            state["best"] = candidate
        last_checkpoint = save_checkpoint(
            args.output_dir, model, optimizer, scheduler, torch, state
        )
        if state["best"]["optimizer_step"] == state["completed_steps"]:
            state["best"]["checkpoint"] = str(last_checkpoint.relative_to(args.output_dir))
            write_json(args.output_dir / "best-checkpoint.json", state["best"])
        model.train()
        if time.monotonic() - segment_started >= args.segment_seconds:
            print(json.dumps({
                "status": "segment_completed",
                "checkpoint": str(last_checkpoint),
                "completed_steps": state["completed_steps"],
            }, sort_keys=True), flush=True)
            return

    require(state["completed_steps"] == total_steps, "training step denominator mismatch")
    best = json.loads((args.output_dir / "best-checkpoint.json").read_text(encoding="utf-8"))
    best_adapter = args.output_dir / best["checkpoint"] / "adapter" / "adapter_model.safetensors"
    require(best_adapter.is_file(), "best adapter missing")
    summary = {
        "version": "a3-sft-formal-training-v1",
        "status": "completed",
        "mode": "nf4_qlora",
        "epochs": config["training"]["epochs"],
        "train_examples": len(encoded["train"]),
        "validation_examples": len(encoded["validation"]),
        "optimizer_steps": state["completed_steps"],
        "micro_steps": state["micro_steps"],
        "mean_train_loss": state["train_loss_sum"] / state["micro_steps"],
        "best": best,
        "best_adapter_sha256": sha256_file(best_adapter),
        "training_order_sha256": sha256_json(order_ids),
        "peak_gpu_memory_bytes": state["peak_gpu_memory_bytes"],
        "finished_at": utc_now(),
    }
    write_json(args.output_dir / "training-summary.json", summary)
    manifest = {
        "schema_version": "0.1.0",
        "run_id": f"a33_sft_nf4_s{config['seed']}",
        "stage": "sft",
        "started_at": state["started_at"],
        "finished_at": utc_now(),
        "git_commit": commit,
        "dirty_worktree": False,
        "config_sha256": sha256_file(args.config),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "model_config_sha256": config["model"]["config_sha256"],
        "adapter_sha256": summary["best_adapter_sha256"],
        "dataset_manifest_sha256": lock["data_files"]["dataset-manifest.json"],
        "environment_sha256": sha256_file(args.environment_lock),
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": None,
        "execution_artifact_sha256": sha256_file(args.output_dir / "training-summary.json"),
        "notes": f"best_checkpoint={best['checkpoint']}; data_lock={state['data_lock_sha256']}",
    }
    schema = json.loads((repo / "schemas/run-manifest-v0.1.schema.json").read_text())
    from jsonschema import Draft202012Validator
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(manifest)
    write_json(completed_marker, manifest)
    print(json.dumps(summary, sort_keys=True), flush=True)

    del optimizer, scheduler, model, base
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
