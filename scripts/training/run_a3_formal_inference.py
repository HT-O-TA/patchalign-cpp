"""Segmented deterministic inference for A3.3 M0 and SFT models."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from typing import Any

from jsonschema import Draft202012Validator

from patchalign.evaluation.patches import PatchParseError, parse_unified_diff
from scripts.baseline.run_a3_baseline import (
    generate_one,
    load_cases,
    prompt_sha256,
    render_model_input,
)
from scripts.training.a3_formal_common import (
    require,
    sha256_file,
    validate_config,
    verify_lock,
    write_json,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_model(model_path: Path, role: str, adapter_dir: Path | None) -> Any:
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    base = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
        low_cpu_mem_usage=True,
        device_map={"": 0},
        dtype=torch.bfloat16,
        quantization_config=quantization,
    )
    if role == "m0":
        model = base
    else:
        from peft import PeftModel
        require(adapter_dir is not None, "SFT adapter directory missing")
        model = PeftModel.from_pretrained(base, adapter_dir, is_trainable=False)
    model.config.use_cache = True
    model.eval()
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--role", choices=("m0", "sft"), required=True)
    parser.add_argument("--training-dir", type=Path)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--segment-seconds", type=int, default=27600)
    args = parser.parse_args()
    require(args.segment_seconds >= 600, "segment must allow at least 600 seconds")
    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    lock = verify_lock(args.config, config)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(),
        "formal inference requires a clean worktree",
    )
    require(args.environment_lock.is_file(), "environment lock missing")
    if (args.output_dir / "run-manifest.json").exists():
        print(json.dumps({"status": "already_completed", "output": str(args.output_dir)}, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)

    adapter_dir: Path | None = None
    adapter_sha: str | None = None
    training_manifest: dict[str, Any] | None = None
    if args.role == "sft":
        require(args.training_dir is not None, "--training-dir is required for SFT")
        training_manifest_path = args.training_dir / "training-manifest.json"
        require(training_manifest_path.is_file(), "formal training is not complete")
        training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
        require(training_manifest["git_commit"] == commit, "training/inference commit mismatch")
        require(training_manifest["config_sha256"] == sha256_file(args.config), "training/inference config mismatch")
        best = json.loads((args.training_dir / "best-checkpoint.json").read_text(encoding="utf-8"))
        adapter_dir = args.training_dir / best["checkpoint"] / "adapter"
        adapter_sha = sha256_file(adapter_dir / "adapter_model.safetensors")
        require(adapter_sha == training_manifest["adapter_sha256"], "best adapter hash mismatch")

    state_path = args.output_dir / "inference-state.json"
    expected_state = {
        "version": "a3-formal-inference-state-v1",
        "role": args.role,
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "data_lock_sha256": sha256_file(
            Path(config["data"]["root"]) / config["data"]["freeze_lock"]
        ),
        "adapter_sha256": adapter_sha,
    }
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for key, value in expected_state.items():
            require(state[key] == value, f"inference resume mismatch: {key}")
    else:
        state = {**expected_state, "started_at": utc_now()}
        write_json(state_path, state)

    import numpy as np
    import torch
    from transformers import AutoTokenizer
    require(torch.cuda.is_available(), "CUDA unavailable")
    require(torch.cuda.device_count() == 1, "exactly one visible GPU required")
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)

    model_path = Path(config["model"]["local_path"])
    require(
        sha256_file(model_path / "config.json") == config["model"]["config_sha256"],
        "model config hash mismatch",
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    evaluation = config["evaluation"]
    manifest, cases = load_cases(Path(evaluation["holdout_root"]), evaluation["allowed_path"])
    require(manifest["task_level_counts"] == evaluation["required_task_levels"], "holdout composition mismatch")
    require(len(cases) == 500, "formal holdout denominator mismatch")
    prepared = []
    for case in cases:
        rendered = render_model_input(
            tokenizer, case["prompt"], evaluation["input_mode"]
        )
        token_count = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
        require(token_count <= evaluation["generation"]["max_input_tokens"], f"prompt too long: {case['item']['case_id']}")
        prepared.append({**case, "rendered": rendered, "input_tokens": token_count})

    prompt_records = [
        {
            "case_id": case["item"]["case_id"],
            "task_level": case["item"]["task_level"],
            "prompt_version": evaluation["prompt_version"],
            "prompt_sha256": prompt_sha256(case["prompt"]),
            "prompt_text": case["prompt"],
            "public_test_id": case["public_test_id"],
            "rendered_input_tokens": case["input_tokens"],
        }
        for case in prepared
    ]
    prompts_text = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in prompt_records)
    prompts_path = args.output_dir / "prompts.jsonl"
    if prompts_path.exists():
        require(prompts_path.read_text(encoding="utf-8") == prompts_text, "prompt artifact changed")
    else:
        prompts_path.write_text(prompts_text, encoding="utf-8")

    partial_path = args.output_dir / "predictions.partial.jsonl"
    records = []
    if partial_path.exists():
        records = [
            json.loads(line)
            for line in partial_path.read_text(encoding="utf-8").splitlines()
        ]
    require(len(records) <= len(prepared), "too many partial predictions")
    require(
        [record["sample_id"] for record in records]
        == [case["item"]["case_id"] for case in prepared[:len(records)]],
        "partial prediction order mismatch",
    )

    load_started = time.monotonic()
    model = load_model(model_path, args.role, adapter_dir)
    load_seconds = time.monotonic() - load_started
    segment_started = time.monotonic()
    run_id = f"a33_{args.role}_nf4_s{config['seed']}"
    prediction_schema = json.loads((repo / "schemas/prediction-v0.1.schema.json").read_text())
    validator = Draft202012Validator(prediction_schema)
    generation = evaluation["generation"]
    for index in range(len(records), len(prepared)):
        case = prepared[index]
        item = case["item"]
        try:
            result = generate_one(model, tokenizer, torch, case["rendered"], generation)
            raw_text = result["raw_text"]
            try:
                parse_unified_diff(raw_text)
                extracted_patch = raw_text
            except PatchParseError:
                extracted_patch = None
            status, error = "ok", None
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            result = {
                "raw_text": "", "input_tokens": case["input_tokens"], "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch, status, error = None, "oom", f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            result = {
                "raw_text": "", "input_tokens": case["input_tokens"], "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch, status, error = None, "generation_failed", f"{type(exc).__name__}: {exc}"
        record = {
            "schema_version": "0.1.0",
            "run_id": run_id,
            "sample_id": item["case_id"],
            "model": {
                "model_id": config["model"]["model_id"],
                "revision": config["model"]["revision"],
                "config_sha256": config["model"]["config_sha256"],
                "adapter_sha256": adapter_sha,
            },
            "prompt_version": evaluation["prompt_version"],
            "prompt_sha256": prompt_sha256(case["prompt"]),
            "seed": config["seed"],
            "generation": generation,
            "raw_text": result["raw_text"],
            "extracted_patch": extracted_patch,
            "status": status,
            "error": error,
            "input_tokens": int(result["input_tokens"]),
            "output_tokens": int(result["output_tokens"]),
            "latency_seconds": float(result["latency_seconds"]),
            "max_gpu_memory_bytes": int(result["max_gpu_memory_bytes"]),
        }
        validator.validate(record)
        with partial_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        records.append(record)
        print(json.dumps({
            "role": args.role, "index": index + 1, "total": len(prepared),
            "case": item["case_id"], "status": status,
        }, sort_keys=True), flush=True)
        if time.monotonic() - segment_started >= args.segment_seconds:
            print(json.dumps({"status": "segment_completed", "predictions": len(records)}, sort_keys=True))
            return

    probe_records = []
    for record, case in zip(records[:3], prepared[:3], strict=True):
        require(record["status"] == "ok", f"probe source failed: {record['sample_id']}")
        replay = generate_one(model, tokenizer, torch, case["rendered"], generation)
        stable = replay["raw_text"] == record["raw_text"]
        probe_records.append({
            "case_id": record["sample_id"],
            "stable": stable,
            "first_sha256": "sha256:" + hashlib.sha256(record["raw_text"].encode()).hexdigest(),
            "replay_sha256": "sha256:" + hashlib.sha256(replay["raw_text"].encode()).hexdigest(),
        })
        require(stable, f"nondeterministic generation: {record['sample_id']}")

    predictions_path = args.output_dir / "predictions.jsonl"
    require(not predictions_path.exists(), "refusing to overwrite predictions")
    partial_path.rename(predictions_path)
    write_json(args.output_dir / "determinism-probe.json", probe_records)
    summary = {
        "version": "a3-formal-generation-v1",
        "role": args.role,
        "cases": len(records),
        "status_counts": dict(Counter(record["status"] for record in records)),
        "strict_diff_count": sum(record["extracted_patch"] is not None for record in records),
        "input_tokens": sum(record["input_tokens"] for record in records),
        "output_tokens": sum(record["output_tokens"] for record in records),
        "generation_seconds": sum(record["latency_seconds"] for record in records),
        "model_load_seconds_last_segment": load_seconds,
        "peak_gpu_memory_bytes": max(record["max_gpu_memory_bytes"] for record in records),
        "determinism_probe_count": 3,
        "determinism_probe_stable": all(item["stable"] for item in probe_records),
    }
    write_json(args.output_dir / "generation-summary.json", summary)
    run_manifest = {
        "schema_version": "0.1.0",
        "run_id": run_id,
        "stage": "baseline" if args.role == "m0" else "sft",
        "started_at": state["started_at"],
        "finished_at": utc_now(),
        "git_commit": commit,
        "dirty_worktree": False,
        "config_sha256": sha256_file(args.config),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "model_config_sha256": config["model"]["config_sha256"],
        "adapter_sha256": adapter_sha,
        "dataset_manifest_sha256": lock["holdout_files"]["a2-manifest.json"],
        "environment_sha256": sha256_file(args.environment_lock),
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": sha256_file(predictions_path),
        "execution_artifact_sha256": None,
        "notes": f"role={args.role}; quantization=nf4; prompts={sha256_file(prompts_path)}",
    }
    run_schema = json.loads((repo / "schemas/run-manifest-v0.1.schema.json").read_text())
    Draft202012Validator(run_schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(run_manifest)
    write_json(args.output_dir / "run-manifest.json", run_manifest)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
