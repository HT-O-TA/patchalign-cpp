from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import time
from pathlib import Path

os.environ.setdefault("PYTHONNOUSERSITE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import accelerate
import bitsandbytes as bnb
import datasets
import peft
import torch
import transformers
import trl
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


LORA_TARGETS = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release(*objects: object) -> None:
    for obj in objects:
        del obj
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()


def make_batch(tokenizer: object, device: torch.device) -> tuple[dict[str, torch.Tensor], torch.Tensor, dict[str, torch.Tensor]]:
    prompt = (
        "Repair the localized C++ defect. Output only a unified diff.\n"
        "File: main.cpp\n"
        "Bug: add should return the sum of a and b.\n"
        "Code:\nint add(int a, int b) { return a - b; }\n"
    )
    target = (
        "--- a/main.cpp\n"
        "+++ b/main.cpp\n"
        "@@ -1 +1 @@\n"
        "-int add(int a, int b) { return a - b; }\n"
        "+int add(int a, int b) { return a + b; }\n"
    )
    eos = tokenizer.eos_token or ""
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    encoded = tokenizer(
        prompt + target + eos,
        add_special_tokens=False,
        return_tensors="pt",
        truncation=True,
        max_length=256,
    )
    labels = encoded["input_ids"].clone()
    labels[:, : min(len(prompt_ids), labels.shape[1])] = -100
    require((labels != -100).any().item(), "all training labels were masked")
    batch = {key: value.to(device) for key, value in encoded.items()}
    labels = labels.to(device)
    generation = tokenizer(
        prompt,
        add_special_tokens=False,
        return_tensors="pt",
        truncation=True,
        max_length=192,
    )
    generation = {key: value.to(device) for key, value in generation.items()}
    return batch, labels, generation


def load_model(model_path: str, phase: str) -> torch.nn.Module:
    common = {
        "pretrained_model_name_or_path": model_path,
        "local_files_only": True,
        "low_cpu_mem_usage": True,
        "device_map": {"": 0},
    }
    if phase == "bf16":
        return AutoModelForCausalLM.from_pretrained(
            **common,
            torch_dtype=torch.bfloat16,
        )
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    return AutoModelForCausalLM.from_pretrained(
        **common,
        quantization_config=quantization,
        torch_dtype=torch.bfloat16,
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.time()
    require(os.environ.get("PYTHONNOUSERSITE") == "1", "PYTHONNOUSERSITE is not set")
    require(torch.cuda.is_available(), "CUDA is unavailable")
    require(torch.cuda.device_count() == 1, "smoke expects exactly one visible GPU")
    require(torch.cuda.is_bf16_supported(), "allocated GPU does not support BF16")
    device = torch.device("cuda:0")
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.cuda.reset_peak_memory_stats(device)

    model_root = Path(args.model_path).resolve()
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    require(model_root.is_dir(), f"model directory is missing: {model_root}")
    for name in ("config.json", "tokenizer_config.json", "model.safetensors.index.json"):
        require((model_root / name).is_file(), f"required model file is missing: {name}")

    config = AutoConfig.from_pretrained(str(model_root), local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_root), local_files_only=True, use_fast=True
    )
    require(config.model_type == "qwen2", f"unexpected model_type: {config.model_type}")
    require(config.architectures == ["Qwen2ForCausalLM"], f"unexpected architecture: {config.architectures}")
    require(config.vocab_size == 152064, f"unexpected vocab size: {config.vocab_size}")
    probe = tokenizer.encode("int add(int a, int b)", add_special_tokens=False)
    require(len(probe) > 0, "tokenizer returned an empty encoding")

    matrix_a = torch.randn(256, 256, device=device, dtype=torch.bfloat16, requires_grad=True)
    matrix_b = torch.randn(256, 256, device=device, dtype=torch.bfloat16)
    matrix_loss = (matrix_a @ matrix_b).float().square().mean()
    require(torch.isfinite(matrix_loss).item(), "BF16 matrix loss is not finite")
    matrix_loss.backward()
    require(matrix_a.grad is not None, "BF16 matrix backward produced no gradients")
    bf16_checksum = float(matrix_loss.item())
    release(matrix_a, matrix_b, matrix_loss)

    load_started = time.time()
    model = load_model(str(model_root), args.phase)
    load_seconds = time.time() - load_started
    model.config.use_cache = False
    model_footprint = int(model.get_memory_footprint())

    if args.phase == "nf4":
        require(getattr(model, "is_loaded_in_4bit", False), "model did not report 4-bit loading")
        linear4_count = sum(1 for module in model.modules() if isinstance(module, bnb.nn.Linear4bit))
        require(linear4_count > 0, "no bitsandbytes Linear4bit modules were found")
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)
    else:
        linear4_count = 0

    lora_config = LoraConfig(
        task_type="CAUSAL_LM",
        r=8,
        lora_alpha=16,
        lora_dropout=0.0,
        bias="none",
        target_modules=LORA_TARGETS,
    )
    model = get_peft_model(model, lora_config)
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total = sum(parameter.numel() for parameter in model.parameters())
    require(trainable > 0, "LoRA injection produced no trainable parameters")
    require(trainable < total, "base model was not frozen")

    batch, labels, generation_inputs = make_batch(tokenizer, device)
    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=1e-4,
    )
    model.train()
    output = model(**batch, labels=labels)
    loss = output.loss
    require(torch.isfinite(loss).item(), "training loss is not finite")
    loss.backward()
    squared_grad_norm = 0.0
    parameters_with_grad = 0
    for parameter in model.parameters():
        if parameter.requires_grad and parameter.grad is not None:
            require(torch.isfinite(parameter.grad).all().item(), "adapter gradient is not finite")
            squared_grad_norm += float(parameter.grad.float().square().sum().item())
            parameters_with_grad += 1
    require(parameters_with_grad > 0, "no trainable parameter received a gradient")
    grad_norm = squared_grad_norm**0.5
    require(grad_norm > 0.0, "adapter gradient norm is zero")
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)

    adapter_dir = output_root / f"{args.phase}-adapter"
    model.save_pretrained(adapter_dir, safe_serialization=True)
    require((adapter_dir / "adapter_config.json").is_file(), "adapter config was not saved")
    require((adapter_dir / "adapter_model.safetensors").is_file(), "adapter weights were not saved")
    adapter_hash = sha256(adapter_dir / "adapter_model.safetensors")
    loss_value = float(loss.detach().float().item())
    del output, loss, optimizer, batch, labels, model
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    reload_started = time.time()
    reload_base = load_model(str(model_root), args.phase)
    reloaded = PeftModel.from_pretrained(reload_base, adapter_dir, is_trainable=False)
    reloaded.config.use_cache = True
    reloaded.eval()
    with torch.inference_mode():
        logits = reloaded(**generation_inputs).logits
        require(torch.isfinite(logits).all().item(), "reloaded adapter logits are not finite")
        generated = reloaded.generate(
            **generation_inputs,
            do_sample=False,
            max_new_tokens=16,
            pad_token_id=tokenizer.eos_token_id,
        )
    reload_seconds = time.time() - reload_started
    generated_text = tokenizer.decode(
        generated[0, generation_inputs["input_ids"].shape[1] :],
        skip_special_tokens=True,
    )

    result = {
        "status": "ok",
        "phase": args.phase,
        "seed": args.seed,
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "node": platform.node(),
        "gpu": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "bf16_supported": torch.cuda.is_bf16_supported(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "datasets": datasets.__version__,
        "accelerate": accelerate.__version__,
        "peft": peft.__version__,
        "trl": trl.__version__,
        "bitsandbytes": bnb.__version__,
        "model_path": str(model_root),
        "config_sha256": sha256(model_root / "config.json"),
        "weight_index_sha256": sha256(model_root / "model.safetensors.index.json"),
        "model_footprint_bytes": model_footprint,
        "linear4_modules": linear4_count,
        "trainable_parameters": trainable,
        "total_parameters": total,
        "trainable_fraction": trainable / total,
        "bf16_matrix_checksum": bf16_checksum,
        "loss": loss_value,
        "adapter_gradient_norm": grad_norm,
        "adapter_sha256": adapter_hash,
        "generated_text": generated_text,
        "load_seconds": load_seconds,
        "reload_and_generate_seconds": reload_seconds,
        "elapsed_seconds": time.time() - started,
        "max_memory_allocated_bytes": torch.cuda.max_memory_allocated(device),
        "max_memory_reserved_bytes": torch.cuda.max_memory_reserved(device),
    }
    result_path = output_root / f"{args.phase}-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("bf16", "nf4"), required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=20260830)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
