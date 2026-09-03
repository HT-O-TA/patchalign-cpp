"""Reload one A3.2 adapter and generate predictions on the frozen A2 holdout."""

from __future__ import annotations

import argparse
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
from scripts.training.train_a3_sft_pilot import (
    MODES,
    require,
    sha256_file,
    validate_config,
    write_json,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_state(repo: Path) -> tuple[str, bool]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip()
    )
    return commit, dirty


def load_inference_model(model_path: Path, adapter_dir: Path, mode: str) -> Any:
    import torch
    from peft import PeftModel
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
        base = AutoModelForCausalLM.from_pretrained(**common)
    else:
        base = AutoModelForCausalLM.from_pretrained(
            **common,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            ),
        )
    model = PeftModel.from_pretrained(base, adapter_dir, is_trainable=False)
    model.config.use_cache = True
    model.eval()
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument("--training-manifest", type=Path, required=True)
    parser.add_argument("--holdout-dir", type=Path, required=True)
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
    require(not dirty, "refusing reportable inference from a dirty worktree")
    require(not args.output_dir.exists(), f"refusing to overwrite {args.output_dir}")
    require(args.environment_lock.is_file(), "environment lock is missing")

    training_manifest = json.loads(args.training_manifest.read_text(encoding="utf-8"))
    require(training_manifest["git_commit"] == commit, "training/inference git mismatch")
    require(
        training_manifest["config_sha256"] == sha256_file(args.config),
        "training config hash mismatch",
    )
    require(
        training_manifest["adapter_sha256"]
        == sha256_file(args.adapter_dir / "adapter_model.safetensors"),
        "adapter hash mismatch",
    )
    require(f"mode={args.mode}" in training_manifest["notes"], "training mode mismatch")
    require(
        sha256_file(args.holdout_dir / "a2-manifest.json")
        == config["evaluation"]["holdout_manifest_sha256"],
        "A2 holdout manifest hash mismatch",
    )
    args.output_dir.mkdir(parents=True)

    import numpy as np
    import torch
    from transformers import AutoTokenizer

    require(torch.cuda.is_available(), "CUDA is unavailable")
    require(torch.cuda.device_count() == 1, "pilot expects exactly one visible GPU")
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
    manifest, cases = load_cases(args.holdout_dir, evaluation["allowed_path"])
    require(
        manifest["task_level_counts"] == {"function": 50, "file_window": 20},
        "A2 holdout composition changed",
    )
    prepared = []
    for case in cases:
        rendered = render_model_input(tokenizer, case["prompt"], "raw_completion")
        token_count = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
        require(
            token_count <= evaluation["generation"]["max_input_tokens"],
            f"evaluation prompt too long: {case['item']['case_id']}={token_count}",
        )
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
    (args.output_dir / "prompts.jsonl").write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in prompt_records
        )
        + "\n",
        encoding="utf-8",
    )

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_started = time.monotonic()
    model = load_inference_model(model_path, args.adapter_dir, args.mode)
    load_seconds = time.monotonic() - load_started
    started_at = utc_now()
    run_id = training_manifest["run_id"] + "_inference"
    adapter_sha = training_manifest["adapter_sha256"]
    prediction_schema = json.loads(
        (repo / "schemas/prediction-v0.1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(prediction_schema)
    records = []
    rendered_by_case = {}
    generation = evaluation["generation"]
    for index, case in enumerate(prepared, start=1):
        item = case["item"]
        try:
            result = generate_one(model, tokenizer, torch, case["rendered"], generation)
            raw_text = result["raw_text"]
            try:
                parse_unified_diff(raw_text)
                extracted_patch = raw_text
            except PatchParseError:
                extracted_patch = None
            status = "ok"
            error = None
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            result = {
                "raw_text": "",
                "input_tokens": case["input_tokens"],
                "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch = None
            status = "oom"
            error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            result = {
                "raw_text": "",
                "input_tokens": case["input_tokens"],
                "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch = None
            status = "generation_failed"
            error = f"{type(exc).__name__}: {exc}"

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
        records.append(record)
        rendered_by_case[item["case_id"]] = case["rendered"]
        print(
            json.dumps(
                {
                    "case": item["case_id"],
                    "index": index,
                    "total": len(prepared),
                    "status": status,
                    "input_tokens": record["input_tokens"],
                    "output_tokens": record["output_tokens"],
                    "latency_seconds": round(record["latency_seconds"], 3),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    probe_records = []
    for record in records[: evaluation["determinism_probe_count"]]:
        require(record["status"] == "ok", f"probe source failed: {record['sample_id']}")
        replay = generate_one(
            model, tokenizer, torch, rendered_by_case[record["sample_id"]], generation
        )
        stable = replay["raw_text"] == record["raw_text"]
        probe_records.append(
            {
                "case_id": record["sample_id"],
                "stable": stable,
                "first_sha256": "sha256:"
                + hashlib.sha256(record["raw_text"].encode("utf-8")).hexdigest(),
                "replay_sha256": "sha256:"
                + hashlib.sha256(replay["raw_text"].encode("utf-8")).hexdigest(),
            }
        )
        require(stable, f"nondeterministic generation: {record['sample_id']}")

    predictions_path = args.output_dir / "predictions.jsonl"
    predictions_path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(args.output_dir / "determinism-probe.json", probe_records)
    summary = {
        "version": "a3-sft-pilot-generation-v1",
        "run_id": run_id,
        "mode": args.mode,
        "cases": len(records),
        "status_counts": {
            status: sum(record["status"] == status for record in records)
            for status in ("ok", "generation_failed", "timeout", "oom")
        },
        "strict_diff_count": sum(record["extracted_patch"] is not None for record in records),
        "input_tokens": sum(record["input_tokens"] for record in records),
        "output_tokens": sum(record["output_tokens"] for record in records),
        "generation_seconds": sum(record["latency_seconds"] for record in records),
        "model_load_seconds": load_seconds,
        "peak_gpu_memory_bytes": max(
            (record["max_gpu_memory_bytes"] or 0) for record in records
        ),
        "determinism_probe_count": len(probe_records),
        "determinism_probe_stable": all(item["stable"] for item in probe_records),
    }
    write_json(args.output_dir / "generation-summary.json", summary)
    inference_manifest = {
        "schema_version": "0.1.0",
        "run_id": run_id,
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
        "dataset_manifest_sha256": config["evaluation"]["holdout_manifest_sha256"],
        "environment_sha256": sha256_file(args.environment_lock),
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": sha256_file(predictions_path),
        "execution_artifact_sha256": None,
        "notes": (
            f"mode={args.mode}; training_manifest_sha256={sha256_file(args.training_manifest)}; "
            f"prompts_sha256={sha256_file(args.output_dir / 'prompts.jsonl')}; "
            f"generation_summary_sha256={sha256_file(args.output_dir / 'generation-summary.json')}"
        ),
    }
    run_schema = json.loads(
        (repo / "schemas/run-manifest-v0.1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        run_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(inference_manifest)
    write_json(args.output_dir / "run-manifest.json", inference_manifest)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
