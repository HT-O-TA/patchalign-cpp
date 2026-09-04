"""Checkpointed M1 adapter continuation for A3.4/SFT-R2."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time
from typing import Any

from jsonschema import Draft202012Validator

from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.a3_sft_r2_common import (
    validate_config,
    verify_data,
    verify_initial_adapter,
)
from scripts.training.train_a3_sft_formal import save_checkpoint, utc_now
from scripts.training.train_a3_sft_pilot import (
    encode_example,
    load_base_model,
    load_jsonl,
    make_batch,
    sha256_json,
    training_order,
)


def evaluate_loss(model: Any, encoded: list[dict[str, Any]], torch: Any) -> float:
    model.eval()
    total = 0.0
    with torch.inference_mode():
        for example in encoded:
            batch = make_batch(torch, example)
            loss = model(**batch).loss
            require(torch.isfinite(loss).item(), "non-finite validation loss")
            total += float(loss.float().item())
            del loss, batch
    return total / len(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--segment-seconds", type=int, default=16800)
    args = parser.parse_args()
    require(args.segment_seconds >= 600, "segment must allow at least 600 seconds")
    os.environ.setdefault("PYTHONNOUSERSITE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    records, selection_manifest = verify_data(repo, args.config, config)
    source_adapter, source_manifest = verify_initial_adapter(config)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(),
        "R2 training requires a clean worktree",
    )
    require(args.environment_lock.is_file(), "environment lock missing")
    require(args.preflight.is_file(), "R2 preflight report missing")
    preflight = json.loads(args.preflight.read_text(encoding="utf-8"))
    require(preflight["version"] == "a3-sft-r2-preflight-v1", "wrong R2 preflight version")
    require(preflight["status"] == "passed", "R2 preflight did not pass")
    require(preflight["git_commit"] == commit, "R2 preflight commit mismatch")
    require(preflight["config_sha256"] == sha256_file(args.config), "R2 preflight config mismatch")
    require(
        preflight["environment_sha256"] == sha256_file(args.environment_lock),
        "R2 preflight environment mismatch",
    )
    require(
        sha256_file(Path(config["model"]["local_path"]) / "config.json")
        == config["model"]["config_sha256"],
        "model config hash mismatch",
    )

    completed_marker = args.output_dir / "training-manifest.json"
    if completed_marker.exists():
        manifest = json.loads(completed_marker.read_text(encoding="utf-8"))
        require(manifest["git_commit"] == commit, "completed R2 run commit mismatch")
        require(manifest["config_sha256"] == sha256_file(args.config), "completed R2 run config mismatch")
        print(json.dumps({"status": "already_completed", "output": str(args.output_dir)}, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    segment_started = time.monotonic()

    import numpy as np
    import torch
    from peft import PeftModel
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

    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["local_path"], local_files_only=True,
        trust_remote_code=False, use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    max_tokens = config["training"]["max_sequence_tokens"]
    encoded = {
        split: [encode_example(tokenizer, item, max_tokens) for item in values]
        for split, values in records.items()
    }
    reference_records = load_jsonl(
        Path(config["data"]["reference_validation_root"]) / "validation.jsonl"
    )
    reference_encoded = [encode_example(tokenizer, item, max_tokens) for item in reference_records]
    orders = training_order(len(encoded["train"]), config["training"]["epochs"], config["seed"])
    accumulation = config["training"]["gradient_accumulation_steps"]
    total_steps = sum(math.ceil(len(order) / accumulation) for order in orders)
    require(total_steps == 150, "R2 optimizer-step denominator mismatch")
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
    adapter_to_load = source_adapter if resume_dir is None else resume_dir / "adapter"
    model = PeftModel.from_pretrained(base, adapter_to_load, is_trainable=True)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    require(bool(trainable), "no trainable R2 adapter parameters")
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
        "version": "a3-sft-r2-trainer-state-v1",
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "selection_manifest_sha256": sha256_file(
            Path(config["data"]["root"]) / config["data"]["selection_manifest"]
        ),
        "source_adapter_sha256": config["initialization"]["adapter_sha256"],
        "next_epoch": 0,
        "next_offset": 0,
        "completed_steps": 0,
        "micro_steps": 0,
        "train_loss_sum": 0.0,
        "focused_validation_loss": None,
        "reference_validation_loss_before": None,
        "reference_validation_loss_after": None,
        "best": None,
        "peak_gpu_memory_bytes": 0,
        "started_at": utc_now(),
    }
    if resume_dir is not None:
        loaded = torch.load(resume_dir / "trainer-state.pt", map_location="cuda", weights_only=False)
        for field in (
            "version", "git_commit", "config_sha256",
            "selection_manifest_sha256", "source_adapter_sha256",
        ):
            require(loaded[field] == state[field], f"R2 resume state mismatch: {field}")
        optimizer.load_state_dict(loaded["optimizer"])
        scheduler.load_state_dict(loaded["scheduler"])
        random.setstate(loaded["python_random_state"])
        torch.set_rng_state(loaded["torch_random_state"].cpu())
        torch.cuda.set_rng_state_all([value.cpu() for value in loaded["cuda_random_state"]])
        state = {
            key: value
            for key, value in loaded.items()
            if key not in {
                "optimizer", "scheduler", "python_random_state",
                "torch_random_state", "cuda_random_state",
            }
        }
    else:
        state["reference_validation_loss_before"] = evaluate_loss(
            model, reference_encoded, torch
        )

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
                require(torch.isfinite(loss).item(), "non-finite R2 training loss")
                (loss / len(group)).backward()
                value = float(loss.detach().float().item())
                losses.append(value)
                state["train_loss_sum"] += value
                state["micro_steps"] += 1
                del output, loss, batch
            grad_norm = torch.nn.utils.clip_grad_norm_(
                trainable, config["training"]["max_grad_norm"]
            )
            require(torch.isfinite(grad_norm).item(), "non-finite R2 gradient norm")
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
            segment_expired = time.monotonic() - segment_started >= args.segment_seconds
            if state["completed_steps"] % checkpoint_every == 0 or segment_expired:
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

        focused_loss = evaluate_loss(model, encoded["validation"], torch)
        reference_after = evaluate_loss(model, reference_encoded, torch)
        state["focused_validation_loss"] = focused_loss
        state["reference_validation_loss_after"] = reference_after
        state["next_epoch"] = epoch_index + 1
        state["next_offset"] = 0
        candidate = {
            "focused_validation_loss": focused_loss,
            "reference_validation_loss": reference_after,
            "optimizer_step": state["completed_steps"],
            "epoch": epoch_index + 1,
        }
        state["best"] = candidate
        last_checkpoint = save_checkpoint(
            args.output_dir, model, optimizer, scheduler, torch, state,
            tag=f"epoch-{epoch_index + 1}",
        )
        state["best"]["checkpoint"] = str(last_checkpoint.relative_to(args.output_dir))
        write_json(args.output_dir / "best-checkpoint.json", state["best"])
        model.train()

    require(state["completed_steps"] == total_steps, "R2 completed step mismatch")
    best = json.loads((args.output_dir / "best-checkpoint.json").read_text(encoding="utf-8"))
    best_adapter = args.output_dir / best["checkpoint"] / "adapter" / "adapter_model.safetensors"
    require(best_adapter.is_file(), "R2 best adapter missing")
    summary = {
        "version": "a3-sft-r2-training-v1",
        "status": "completed",
        "mode": config["training"]["mode"],
        "epochs": config["training"]["epochs"],
        "train_examples": len(encoded["train"]),
        "validation_examples": len(encoded["validation"]),
        "reference_validation_examples": len(reference_encoded),
        "optimizer_steps": state["completed_steps"],
        "micro_steps": state["micro_steps"],
        "mean_train_loss": state["train_loss_sum"] / state["micro_steps"],
        "reference_validation_loss_before": state["reference_validation_loss_before"],
        "reference_validation_loss_after": state["reference_validation_loss_after"],
        "reference_validation_loss_delta": (
            state["reference_validation_loss_after"]
            - state["reference_validation_loss_before"]
        ),
        "best": best,
        "best_adapter_sha256": sha256_file(best_adapter),
        "source_adapter_sha256": config["initialization"]["adapter_sha256"],
        "training_order_sha256": sha256_json(order_ids),
        "peak_gpu_memory_bytes": state["peak_gpu_memory_bytes"],
        "finished_at": utc_now(),
    }
    write_json(args.output_dir / "training-summary.json", summary)
    manifest = {
        "schema_version": "0.1.0",
        "run_id": f"a34_sft_r2_nf4_s{config['seed']}",
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
        "dataset_manifest_sha256": config["data"]["selection_manifest_sha256"],
        "environment_sha256": sha256_file(args.environment_lock),
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": None,
        "execution_artifact_sha256": sha256_file(args.output_dir / "training-summary.json"),
        "notes": (
            f"source_run={source_manifest['run_id']}; "
            f"source_adapter={config['initialization']['adapter_sha256']}; "
            f"best_checkpoint={best['checkpoint']}; "
            f"selection_manifest={config['data']['selection_manifest_sha256']}"
        ),
    }
    run_schema = json.loads((repo / "schemas/run-manifest-v0.1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(
        run_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(manifest)
    write_json(completed_marker, manifest)
    print(json.dumps(summary, sort_keys=True), flush=True)

    del optimizer, scheduler, model, base
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
