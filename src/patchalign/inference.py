"""Application-facing prompt, model inference, and output validation helpers."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path, PurePosixPath
from typing import Any

from patchalign.evaluation.patches import (
    enforce_patch_policy,
    normalize_terminal_lf,
    parse_unified_diff,
)


TASK_LEVELS = {"function", "file_window"}


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    required = {"task_level", "allowed_path", "buggy_code", "public_test"}
    if set(value) != required:
        raise ValueError(f"request fields must be exactly {sorted(required)}")
    if value["task_level"] not in TASK_LEVELS:
        raise ValueError(f"task_level must be one of {sorted(TASK_LEVELS)}")
    allowed_path = value["allowed_path"]
    if not isinstance(allowed_path, str) or not allowed_path:
        raise ValueError("allowed_path must be a non-empty string")
    pure = PurePosixPath(allowed_path)
    if pure.is_absolute() or ".." in pure.parts or "\\" in allowed_path:
        raise ValueError("allowed_path must be a safe repository-relative POSIX path")
    if not isinstance(value["buggy_code"], str) or not value["buggy_code"].strip():
        raise ValueError("buggy_code must be a non-empty string")
    public_test = value["public_test"]
    if not isinstance(public_test, dict) or set(public_test) != {"input", "output"}:
        raise ValueError("public_test must contain exactly input and output")
    if not all(isinstance(public_test[key], str) for key in ("input", "output")):
        raise ValueError("public_test input/output must be strings")
    return value


def build_prompt(request: dict[str, Any]) -> str:
    request = validate_request(request)
    allowed_path = request["allowed_path"]
    public_test = request["public_test"]
    return (
        "Repair the localized C++17 program below.\n"
        "Return exactly one pure unified diff and nothing else.\n"
        "Do not use Markdown fences or explanations. Modify only the allowed file.\n"
        "The diff must use these file markers:\n"
        f"--- a/{allowed_path}\n"
        f"+++ b/{allowed_path}\n\n"
        f"Task level: {request['task_level']}\n"
        f"Allowed file: {allowed_path}\n"
        "No natural-language problem statement is available for this executable sample.\n"
        "Use the buggy code and public failing example as evidence.\n\n"
        "Public failing example input:\n"
        "<input>\n"
        f"{public_test['input'].rstrip(chr(10))}\n"
        "</input>\n"
        "Expected output:\n"
        "<output>\n"
        f"{public_test['output'].rstrip(chr(10))}\n"
        "</output>\n\n"
        f"Buggy file {allowed_path}:\n"
        "<code>\n"
        f"{request['buggy_code'].rstrip(chr(10))}\n"
        "</code>\n\n"
        "Unified diff:\n"
    )


def validate_patch(raw_text: str, allowed_path: str) -> str:
    evaluated, _ = normalize_terminal_lf(raw_text)
    parsed = parse_unified_diff(evaluated)
    enforce_patch_policy(parsed, [allowed_path])
    return evaluated


def generate_patch(
    request: dict[str, Any],
    model_path: Path,
    adapter_path: Path,
    *,
    seed: int = 20260830,
    max_input_tokens: int = 4096,
    max_new_tokens: int = 512,
    local_files_only: bool = True,
) -> dict[str, Any]:
    request = validate_request(request)
    if not (model_path / "config.json").is_file():
        raise FileNotFoundError(f"model config not found: {model_path / 'config.json'}")
    if not (adapter_path / "adapter_model.safetensors").is_file():
        raise FileNotFoundError(f"adapter weights not found: {adapter_path / 'adapter_model.safetensors'}")

    import numpy as np
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("inference requires exactly one visible CUDA GPU")
    import random

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=local_files_only, trust_remote_code=False, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    prompt = build_prompt(request)
    encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=True)
    input_tokens = int(encoded["input_ids"].shape[1])
    if input_tokens > max_input_tokens:
        raise ValueError(f"input token count {input_tokens} exceeds {max_input_tokens}")
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    base = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=local_files_only,
        trust_remote_code=False,
        low_cpu_mem_usage=True,
        device_map={"": 0},
        dtype=torch.bfloat16,
        quantization_config=quantization,
    )
    model = PeftModel.from_pretrained(base, adapter_path, is_trainable=False)
    model.config.use_cache = True
    model.eval()
    encoded = {key: tensor.to(model.device) for key, tensor in encoded.items()}
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.monotonic()
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            do_sample=False,
            num_return_sequences=1,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )
    torch.cuda.synchronize()
    latency = time.monotonic() - started
    new_ids = generated[0, input_tokens:]
    raw_text = tokenizer.decode(new_ids, skip_special_tokens=True)
    patch = validate_patch(raw_text, request["allowed_path"])
    return {
        "patch": patch,
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "patch_sha256": sha256_bytes(patch.encode("utf-8")),
        "input_tokens": input_tokens,
        "output_tokens": int(new_ids.shape[0]),
        "latency_seconds": latency,
        "peak_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
        "seed": seed,
    }
