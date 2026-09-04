"""Segmented deterministic inference for the frozen A3.4/SFT-R2 adapter."""

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

from jsonschema import Draft202012Validator

from patchalign.evaluation.patches import PatchParseError, parse_unified_diff
from scripts.baseline.run_a3_baseline import (
    generate_one,
    load_cases,
    prompt_sha256,
    render_model_input,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.a3_sft_r2_inference_common import (
    validate_config,
    verify_holdout_manifest,
    verify_training_artifact,
)
from scripts.training.run_a3_formal_inference import load_model


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--segment-seconds", type=int, default=27600)
    args = parser.parse_args()
    require(args.segment_seconds >= 600, "segment must allow at least 600 seconds")

    repo = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(),
        "R2 inference requires a clean worktree",
    )
    require(args.config.is_file(), "R2 inference config missing")
    require(args.preflight.is_file(), "R2 inference preflight missing")
    require(args.environment_lock.is_file(), "environment lock missing")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    training = verify_training_artifact(config)
    holdout_manifest = verify_holdout_manifest(config)

    preflight = json.loads(args.preflight.read_text(encoding="utf-8"))
    require(preflight["version"] == "a3-sft-r2-inference-preflight-v1", "wrong inference preflight version")
    require(preflight["status"] == "passed", "R2 inference preflight did not pass")
    require(preflight["git_commit"] == commit, "inference/preflight commit mismatch")
    require(preflight["config_sha256"] == sha256_file(args.config), "inference/preflight config mismatch")
    require(
        preflight["environment_sha256"] == sha256_file(args.environment_lock),
        "inference/preflight environment mismatch",
    )
    require(
        preflight["source_training"]["manifest_sha256"]
        == config["source_training"]["manifest_sha256"],
        "inference/preflight training manifest mismatch",
    )
    require(
        preflight["source_training"]["adapter_sha256"]
        == config["source_training"]["adapter_sha256"],
        "inference/preflight adapter mismatch",
    )
    require(
        preflight["holdout"]["manifest_sha256"] == sha256_file(holdout_manifest),
        "inference/preflight holdout mismatch",
    )
    if (args.output_dir / "run-manifest.json").exists():
        print(json.dumps({"status": "already_completed", "output": str(args.output_dir)}, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)

    adapter_dir = training["adapter_dir"]
    adapter_sha = config["source_training"]["adapter_sha256"]
    state_path = args.output_dir / "inference-state.json"
    expected_state = {
        "version": "a3-sft-r2-inference-state-v1",
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "preflight_sha256": sha256_file(args.preflight),
        "source_training_git_commit": config["source_training"]["git_commit"],
        "source_training_manifest_sha256": config["source_training"]["manifest_sha256"],
        "holdout_manifest_sha256": config["evaluation"]["holdout_manifest_sha256"],
        "adapter_sha256": adapter_sha,
    }
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for key, value in expected_state.items():
            require(state[key] == value, f"R2 inference resume mismatch: {key}")
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
        rendered = render_model_input(tokenizer, case["prompt"], evaluation["input_mode"])
        token_count = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
        require(
            token_count <= evaluation["generation"]["max_input_tokens"],
            f"prompt too long: {case['item']['case_id']}",
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
    prompts_text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in prompt_records
    )
    prompts_path = args.output_dir / "prompts.jsonl"
    if prompts_path.exists():
        require(prompts_path.read_text(encoding="utf-8") == prompts_text, "prompt artifact changed")
    else:
        prompts_path.write_text(prompts_text, encoding="utf-8")
    require(
        sha256_file(prompts_path) == evaluation["prompt_artifact_sha256"],
        "formal prompt artifact hash mismatch",
    )

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
        == [case["item"]["case_id"] for case in prepared[: len(records)]],
        "partial prediction order mismatch",
    )

    load_started = time.monotonic()
    model = load_model(model_path, "sft", adapter_dir)
    load_seconds = time.monotonic() - load_started
    segment_started = time.monotonic()
    run_id = config["run_id"]
    prediction_schema = json.loads(
        (repo / "schemas/prediction-v0.1.schema.json").read_text(encoding="utf-8")
    )
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
                "raw_text": "",
                "input_tokens": case["input_tokens"],
                "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch, status, error = None, "oom", f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            result = {
                "raw_text": "",
                "input_tokens": case["input_tokens"],
                "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch = None
            status, error = "generation_failed", f"{type(exc).__name__}: {exc}"
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
        print(
            json.dumps(
                {
                    "role": "m1-r2",
                    "index": index + 1,
                    "total": len(prepared),
                    "case": item["case_id"],
                    "status": status,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if time.monotonic() - segment_started >= args.segment_seconds:
            print(json.dumps({"status": "segment_completed", "predictions": len(records)}, sort_keys=True))
            return

    probe_records = []
    for record, case in zip(records[:3], prepared[:3], strict=True):
        require(record["status"] == "ok", f"probe source failed: {record['sample_id']}")
        replay = generate_one(model, tokenizer, torch, case["rendered"], generation)
        stable = replay["raw_text"] == record["raw_text"]
        probe_records.append(
            {
                "case_id": record["sample_id"],
                "stable": stable,
                "first_sha256": "sha256:"
                + hashlib.sha256(record["raw_text"].encode()).hexdigest(),
                "replay_sha256": "sha256:"
                + hashlib.sha256(replay["raw_text"].encode()).hexdigest(),
            }
        )
        require(stable, f"nondeterministic generation: {record['sample_id']}")

    predictions_path = args.output_dir / "predictions.jsonl"
    require(not predictions_path.exists(), "refusing to overwrite predictions")
    partial_path.rename(predictions_path)
    write_json(args.output_dir / "determinism-probe.json", probe_records)
    summary = {
        "version": "a3-sft-r2-generation-v1",
        "role": "m1-r2",
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
        "stage": "sft",
        "started_at": state["started_at"],
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
            f"role=m1-r2; quantization=nf4; prompts={sha256_file(prompts_path)}; "
            f"source_training_commit={config['source_training']['git_commit']}; "
            f"source_training_manifest={config['source_training']['manifest_sha256']}; "
            f"preflight={sha256_file(args.preflight)}"
        ),
    }
    run_schema = json.loads(
        (repo / "schemas/run-manifest-v0.1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        run_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(run_manifest)
    write_json(args.output_dir / "run-manifest.json", run_manifest)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
