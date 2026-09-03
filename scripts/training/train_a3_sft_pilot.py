"""Train one frozen A3.2 SFT pilot adapter on the A1 dataset."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time
from typing import Any


MODES = ("bf16_lora", "nf4_qlora")
LORA_TARGETS = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == "a3-sft-pilot-v1", "unexpected pilot config version")
    require(config.get("seed") == 20260830, "unexpected pilot seed")
    model = config["model"]
    require(model["model_id"] == "Qwen/Qwen2.5-Coder-7B", "unexpected model id")
    require(
        model["revision"] == "0396a76181e127dfc13e5c5ec48a8cee09938b02",
        "unexpected model revision",
    )
    training = config["training"]
    expected_shared = {
        "epochs": 1,
        "max_sequence_tokens": 2048,
        "micro_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "learning_rate": 0.0001,
        "warmup_steps": 4,
        "weight_decay": 0.0,
        "max_grad_norm": 1.0,
        "gradient_checkpointing": True,
    }
    for key, expected in expected_shared.items():
        require(training.get(key) == expected, f"unexpected training setting: {key}")
    lora = training["lora"]
    require(
        lora
        == {
            "r": 8,
            "alpha": 16,
            "dropout": 0.0,
            "bias": "none",
            "target_modules": list(LORA_TARGETS),
        },
        "unexpected LoRA configuration",
    )
    require(set(training["modes"]) == set(MODES), "pilot modes changed")
    require(
        training["modes"]["bf16_lora"]
        == {"quantization": "none", "compute_dtype": "bfloat16"},
        "BF16 mode changed",
    )
    require(
        training["modes"]["nf4_qlora"]
        == {
            "quantization": "nf4",
            "compute_dtype": "bfloat16",
            "double_quant": True,
        },
        "NF4 mode changed",
    )
    evaluation = config["evaluation"]
    require(evaluation["scoring_protocol"] == "a3-scoring-v2", "wrong scoring protocol")
    require(evaluation["prompt_version"] == "a3-cpp-repair-v1", "wrong evaluation prompt")
    require(evaluation["allowed_path"] == "main.cpp", "wrong evaluation path")
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
        "unexpected generation configuration",
    )


def build_training_prompt(sample: dict[str, Any]) -> str:
    allowed_path = sample["allowed_paths"][0]
    return (
        "Repair the localized C++17 program below.\n"
        "Return exactly one pure unified diff and nothing else.\n"
        "Do not use Markdown fences or explanations. Modify only the allowed file.\n"
        "The diff must use these file markers:\n"
        f"--- a/{allowed_path}\n"
        f"+++ b/{allowed_path}\n\n"
        f"Task level: {sample['task_level']}\n"
        f"Allowed file: {allowed_path}\n"
        "Problem statement:\n"
        f"{sample['problem_statement'].rstrip(chr(10))}\n\n"
        "Failure evidence:\n"
        f"{sample['failure_evidence'].rstrip(chr(10))}\n\n"
        f"Buggy file {allowed_path}:\n"
        "<code>\n"
        f"{sample['context']['buggy_code'].rstrip(chr(10))}\n"
        "</code>\n\n"
        "Unified diff:\n"
    )


def normalized_target(sample: dict[str, Any]) -> str:
    target = sample["gold_patch"]
    require(isinstance(target, str) and bool(target), f"missing gold patch: {sample['sample_id']}")
    return target if target.endswith("\n") else target + "\n"


def encode_example(
    tokenizer: Any, sample: dict[str, Any], max_sequence_tokens: int
) -> dict[str, Any]:
    prompt = build_training_prompt(sample)
    target = normalized_target(sample)
    prompt_ids = tokenizer(prompt, add_special_tokens=True)["input_ids"]
    target_ids = tokenizer(target, add_special_tokens=False)["input_ids"]
    require(tokenizer.eos_token_id is not None, "tokenizer has no EOS token")
    input_ids = list(prompt_ids) + list(target_ids) + [int(tokenizer.eos_token_id)]
    require(
        len(input_ids) <= max_sequence_tokens,
        f"training sequence exceeds {max_sequence_tokens}: {sample['sample_id']}={len(input_ids)}",
    )
    labels = [-100] * len(prompt_ids) + list(target_ids) + [int(tokenizer.eos_token_id)]
    require(any(value != -100 for value in labels), "all labels are masked")
    return {
        "sample_id": sample["sample_id"],
        "input_ids": input_ids,
        "labels": labels,
        "prompt_tokens": len(prompt_ids),
        "target_tokens": len(target_ids) + 1,
        "sequence_tokens": len(input_ids),
    }


def training_order(count: int, epochs: int, seed: int) -> list[list[int]]:
    require(count > 0 and epochs > 0, "training order requires positive counts")
    generator = random.Random(seed)
    orders = []
    for _ in range(epochs):
        order = list(range(count))
        generator.shuffle(order)
        orders.append(order)
    return orders


def git_state(repo: Path) -> tuple[str, bool]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip()
    )
    return commit, dirty


def make_batch(torch: Any, example: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_ids": torch.tensor([example["input_ids"]], dtype=torch.long, device="cuda"),
        "attention_mask": torch.ones(
            (1, len(example["input_ids"])), dtype=torch.long, device="cuda"
        ),
        "labels": torch.tensor([example["labels"]], dtype=torch.long, device="cuda"),
    }


def load_base_model(model_path: Path, mode: str, gradient_checkpointing: bool) -> Any:
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    common = {
        "pretrained_model_name_or_path": model_path,
        "local_files_only": True,
        "trust_remote_code": False,
        "low_cpu_mem_usage": True,
        "device_map": {"": 0},
        "dtype": torch.bfloat16,
    }
    if mode == "bf16_lora":
        model = AutoModelForCausalLM.from_pretrained(**common)
        if gradient_checkpointing:
            model.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False}
            )
            model.enable_input_require_grads()
        return model
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        **common, quantization_config=quantization
    )
    from peft import prepare_model_for_kbit_training

    return prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=gradient_checkpointing
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    os.environ.setdefault("PYTHONNOUSERSITE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    commit, dirty = git_state(repo)
    require(not dirty, "refusing reportable training from a dirty worktree")
    require(not args.output_dir.exists(), f"refusing to overwrite {args.output_dir}")
    args.output_dir.mkdir(parents=True)
    started_at = utc_now()
    wall_started = time.monotonic()

    model_path = Path(config["model"]["local_path"])
    data_root = Path(config["data"]["root"])
    paths = {
        "manifest": data_root / config["data"]["manifest"],
        "train": data_root / config["data"]["train"],
        "validation": data_root / config["data"]["validation"],
    }
    for name, path in paths.items():
        require(path.is_file(), f"missing {name}: {path}")
        require(
            sha256_file(path) == config["data"][f"{name}_sha256"],
            f"{name} hash mismatch",
        )
    require(
        sha256_file(model_path / "config.json") == config["model"]["config_sha256"],
        "model config hash mismatch",
    )
    require(args.environment_lock.is_file(), "environment lock is missing")

    import numpy as np
    import torch
    from jsonschema import Draft202012Validator
    from peft import LoraConfig, get_peft_model
    from transformers import AutoTokenizer, get_linear_schedule_with_warmup

    require(torch.cuda.is_available(), "CUDA is unavailable")
    require(torch.cuda.device_count() == 1, "pilot expects exactly one visible GPU")
    require(torch.cuda.is_bf16_supported(), "allocated GPU does not support BF16")
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)

    schema = json.loads((repo / "schemas/sample-v0.2.schema.json").read_text())
    validator = Draft202012Validator(schema)
    raw = {name: load_jsonl(paths[name]) for name in ("train", "validation")}
    for split, records in raw.items():
        require(len(records) == config["data"]["expected_counts"][split], f"{split} count mismatch")
        for record in records:
            validator.validate(record)
            require(record["split"] == split, f"wrong split: {record['sample_id']}")
        actual_levels = {
            level: sum(record["task_level"] == level for record in records)
            for level in ("function", "file_window")
        }
        require(
            actual_levels == config["data"]["expected_task_levels"][split],
            f"{split} task-level composition mismatch",
        )

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    max_tokens = config["training"]["max_sequence_tokens"]
    encoded = {
        split: [encode_example(tokenizer, sample, max_tokens) for sample in records]
        for split, records in raw.items()
    }
    token_stats = {
        "version": config["version"],
        "max_sequence_tokens": max_tokens,
        "truncated_examples": 0,
        "splits": {
            split: {
                "count": len(records),
                "min_sequence_tokens": min(item["sequence_tokens"] for item in records),
                "max_sequence_tokens": max(item["sequence_tokens"] for item in records),
                "total_sequence_tokens": sum(item["sequence_tokens"] for item in records),
                "max_prompt_tokens": max(item["prompt_tokens"] for item in records),
                "max_target_tokens": max(item["target_tokens"] for item in records),
            }
            for split, records in encoded.items()
        },
    }
    write_json(args.output_dir / "token-stats.json", token_stats)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    model_load_started = time.monotonic()
    model = load_base_model(
        model_path, args.mode, config["training"]["gradient_checkpointing"]
    )
    model_load_seconds = time.monotonic() - model_load_started
    model.config.use_cache = False
    lora = config["training"]["lora"]
    model = get_peft_model(
        model,
        LoraConfig(
            task_type="CAUSAL_LM",
            r=lora["r"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            bias=lora["bias"],
            target_modules=lora["target_modules"],
        ),
    )
    trainable_parameters = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    require(0 < trainable_parameters < total_parameters, "invalid trainable parameter count")

    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=config["training"]["learning_rate"],
        weight_decay=config["training"]["weight_decay"],
    )
    orders = training_order(
        len(encoded["train"]), config["training"]["epochs"], config["seed"]
    )
    accumulation = config["training"]["gradient_accumulation_steps"]
    optimizer_steps = sum(math.ceil(len(order) / accumulation) for order in orders)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=config["training"]["warmup_steps"],
        num_training_steps=optimizer_steps,
    )
    order_ids = [
        [encoded["train"][index]["sample_id"] for index in order] for order in orders
    ]

    model.train()
    train_loss_sum = 0.0
    micro_steps = 0
    completed_steps = 0
    for epoch, order in enumerate(orders, start=1):
        for start in range(0, len(order), accumulation):
            group = order[start : start + accumulation]
            optimizer.zero_grad(set_to_none=True)
            group_losses = []
            for index in group:
                batch = make_batch(torch, encoded["train"][index])
                output = model(**batch)
                loss = output.loss
                require(torch.isfinite(loss).item(), "non-finite training loss")
                (loss / len(group)).backward()
                loss_value = float(loss.detach().float().item())
                group_losses.append(loss_value)
                train_loss_sum += loss_value
                micro_steps += 1
                del output, loss, batch
            grad_norm = torch.nn.utils.clip_grad_norm_(
                (parameter for parameter in model.parameters() if parameter.requires_grad),
                config["training"]["max_grad_norm"],
            )
            require(torch.isfinite(grad_norm).item(), "non-finite adapter gradient norm")
            optimizer.step()
            scheduler.step()
            completed_steps += 1
            print(
                json.dumps(
                    {
                        "epoch": epoch,
                        "optimizer_step": completed_steps,
                        "optimizer_steps": optimizer_steps,
                        "group_size": len(group),
                        "mean_loss": sum(group_losses) / len(group_losses),
                        "learning_rate": scheduler.get_last_lr()[0],
                        "grad_norm": float(grad_norm),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    model.eval()
    validation_loss_sum = 0.0
    with torch.inference_mode():
        for example in encoded["validation"]:
            batch = make_batch(torch, example)
            loss = model(**batch).loss
            require(torch.isfinite(loss).item(), "non-finite validation loss")
            validation_loss_sum += float(loss.float().item())
            del loss, batch

    adapter_dir = args.output_dir / "adapter"
    model.save_pretrained(adapter_dir, safe_serialization=True)
    adapter_file = adapter_dir / "adapter_model.safetensors"
    require(adapter_file.is_file(), "adapter weights were not saved")
    adapter_sha = sha256_file(adapter_file)
    torch.cuda.synchronize()
    elapsed_seconds = time.monotonic() - wall_started
    summary = {
        "version": config["version"],
        "status": "completed",
        "mode": args.mode,
        "seed": config["seed"],
        "epochs": config["training"]["epochs"],
        "train_examples": len(encoded["train"]),
        "validation_examples": len(encoded["validation"]),
        "micro_steps": micro_steps,
        "optimizer_steps": completed_steps,
        "mean_train_loss": train_loss_sum / micro_steps,
        "mean_validation_loss": validation_loss_sum / len(encoded["validation"]),
        "trainable_parameters": trainable_parameters,
        "total_parameters": total_parameters,
        "trainable_fraction": trainable_parameters / total_parameters,
        "training_order_sha256": sha256_json(order_ids),
        "adapter_sha256": adapter_sha,
        "model_load_seconds": model_load_seconds,
        "elapsed_seconds": elapsed_seconds,
        "peak_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
        "gpu_name": torch.cuda.get_device_name(0),
    }
    write_json(args.output_dir / "training-summary.json", summary)
    manifest = {
        "schema_version": "0.1.0",
        "run_id": (
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}_"
            f"a32_{args.mode}_{sha256_file(args.config)[7:15]}_"
            f"{config['data']['train_sha256'][7:15]}_s{config['seed']}"
        ),
        "stage": "sft_pilot",
        "started_at": started_at,
        "finished_at": utc_now(),
        "git_commit": commit,
        "dirty_worktree": False,
        "config_sha256": sha256_file(args.config),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "model_config_sha256": config["model"]["config_sha256"],
        "adapter_sha256": adapter_sha,
        "dataset_manifest_sha256": config["data"]["manifest_sha256"],
        "environment_sha256": sha256_file(args.environment_lock),
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": None,
        "execution_artifact_sha256": sha256_file(args.output_dir / "training-summary.json"),
        "notes": (
            f"mode={args.mode}; train_sha256={config['data']['train_sha256']}; "
            f"validation_sha256={config['data']['validation_sha256']}; "
            f"token_stats_sha256={sha256_file(args.output_dir / 'token-stats.json')}"
        ),
    }
    manifest_schema = json.loads(
        (repo / "schemas/run-manifest-v0.1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        manifest_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(manifest)
    write_json(args.output_dir / "training-manifest.json", manifest)
    print(json.dumps(summary, sort_keys=True), flush=True)

    del optimizer, scheduler, model
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
