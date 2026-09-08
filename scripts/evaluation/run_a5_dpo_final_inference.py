#!/usr/bin/env python3
"""Segmented deterministic inference for the selected A5 DPO adapter."""

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
from scripts.baseline.run_a3_baseline import generate_one, load_cases, prompt_sha256, render_model_input
from scripts.evaluation.a5_dpo_final_common import (
    DATASETS,
    inference_dir,
    read_json,
    read_jsonl,
    validate_config,
    verify_dataset,
    verify_selection_and_adapter,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.run_a3_formal_inference import load_model


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--segment-seconds", type=int, default=27600)
    args = parser.parse_args()
    require(args.segment_seconds >= 600, "segment must allow at least 600 seconds")
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 final inference requires a clean worktree")
    require(args.output_dir == inference_dir(config, args.dataset), "unexpected A5 final inference directory")
    if (args.output_dir / "run-manifest.json").exists():
        print(json.dumps({"status": "already_completed", "output": str(args.output_dir)}, sort_keys=True))
        return
    preflight = read_json(args.preflight)
    require(preflight["version"] == "a5-dpo-final-preflight-v1" and preflight["status"] == "passed", "A5 final preflight not passed")
    require(preflight["git_commit"] == commit, "A5 final preflight commit mismatch")
    require(preflight["config_sha256"] == sha256_file(args.config), "A5 final preflight config mismatch")
    require(preflight["selection_sha256"] == config["selection"]["sha256"], "A5 final preflight selection mismatch")
    verify_selection_and_adapter(config)
    root, manifest = verify_dataset(config, args.dataset)
    dataset = config["datasets"][args.dataset]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    from transformers import AutoTokenizer
    import numpy as np
    import torch

    require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "exactly one CUDA GPU required")
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)
    tokenizer = AutoTokenizer.from_pretrained(config["model"]["local_path"], local_files_only=True, trust_remote_code=False, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    prepared = []
    prompt_rows = []
    if dataset["kind"] == "cpp":
        _, cases = load_cases(root, dataset["allowed_path"], dataset["manifest"])
        for case in cases:
            rendered = render_model_input(tokenizer, case["prompt"], dataset["input_mode"])
            count = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
            prepared.append({"case_id": case["item"]["case_id"], "prompt": case["prompt"], "rendered": rendered, "input_tokens": count})
            prompt_rows.append({
                "case_id": case["item"]["case_id"],
                "task_level": case["item"]["task_level"],
                "prompt_version": dataset["prompt_version"],
                "prompt_sha256": prompt_sha256(case["prompt"]),
                "prompt_text": case["prompt"],
                "public_test_id": case["public_test_id"],
                "rendered_input_tokens": count,
            })
        prompts_text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in prompt_rows)
    else:
        source_prompts = root / dataset["prompts"]
        prompt_rows = read_jsonl(source_prompts)
        require([row["case_id"] for row in prompt_rows] == [row["case_id"] for row in manifest["cases"]], "Defects4C prompt order changed")
        for row in prompt_rows:
            count = len(tokenizer(row["prompt_text"], add_special_tokens=True)["input_ids"])
            require(count == row["input_tokens"], f"Defects4C token count changed: {row['case_id']}")
            prepared.append({"case_id": row["case_id"], "prompt": row["prompt_text"], "rendered": row["prompt_text"], "input_tokens": count})
        prompts_text = source_prompts.read_text(encoding="utf-8")
    require(len(prepared) == dataset["case_count"], "A5 final inference denominator changed")
    require(max(row["input_tokens"] for row in prepared) <= config["generation"]["max_input_tokens"], "A5 final prompt exceeds token limit")
    prompts_path = args.output_dir / "prompts.jsonl"
    if prompts_path.exists():
        require(prompts_path.read_text(encoding="utf-8") == prompts_text, "A5 final prompt artifact changed")
    else:
        prompts_path.write_text(prompts_text, encoding="utf-8", newline="\n")
    require(sha256_file(prompts_path) == dataset["prompt_artifact_sha256"], "A5 final prompt artifact hash mismatch")

    state_path = args.output_dir / "inference-state.json"
    expected_state = {
        "version": "a5-dpo-final-inference-state-v1",
        "dataset": args.dataset,
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "preflight_sha256": sha256_file(args.preflight),
        "dataset_manifest_sha256": dataset["manifest_sha256"],
        "adapter_sha256": config["adapter"]["sha256"],
    }
    if state_path.exists():
        state = read_json(state_path)
        for key, value in expected_state.items():
            require(state[key] == value, f"A5 final inference resume mismatch: {key}")
    else:
        state = {**expected_state, "started_at": utc_now()}
        write_json(state_path, state)

    partial_path = args.output_dir / "predictions.partial.jsonl"
    records = [] if not partial_path.exists() else read_jsonl(partial_path)
    require(len(records) <= len(prepared), "too many A5 final partial predictions")
    require([row["sample_id"] for row in records] == [row["case_id"] for row in prepared[:len(records)]], "A5 final partial prediction order changed")
    load_started = time.monotonic()
    model = load_model(Path(config["model"]["local_path"]), "sft", Path(config["adapter"]["path"]))
    load_seconds = time.monotonic() - load_started
    segment_started = time.monotonic()
    generation = {key: config["generation"][key] for key in ("do_sample", "temperature", "top_p", "num_return_sequences", "max_input_tokens", "max_new_tokens")}
    validator = Draft202012Validator(read_json(repo / "schemas/prediction-v0.1.schema.json"))
    for index in range(len(records), len(prepared)):
        case = prepared[index]
        try:
            result = generate_one(model, tokenizer, torch, case["rendered"], generation)
            raw_text = result["raw_text"]
            try:
                parse_unified_diff(raw_text)
                extracted, status, error = raw_text, "ok", None
            except PatchParseError:
                extracted, status, error = None, "ok", None
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            result = {"raw_text": "", "input_tokens": case["input_tokens"], "output_tokens": 0, "latency_seconds": 0.0, "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated())}
            raw_text, extracted, status, error = "", None, "oom", f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            result = {"raw_text": "", "input_tokens": case["input_tokens"], "output_tokens": 0, "latency_seconds": 0.0, "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated())}
            raw_text, extracted, status, error = "", None, "generation_failed", f"{type(exc).__name__}: {exc}"
        record = {
            "schema_version": "0.1.0",
            "run_id": f"a5_final_{args.dataset}_beta03_s{config['seed']}",
            "sample_id": case["case_id"],
            "model": {"model_id": config["model"]["model_id"], "revision": config["model"]["revision"], "config_sha256": config["model"]["config_sha256"], "adapter_sha256": config["adapter"]["sha256"]},
            "prompt_version": dataset["prompt_version"],
            "prompt_sha256": prompt_sha256(case["prompt"]),
            "seed": config["seed"],
            "generation": generation,
            "raw_text": raw_text,
            "extracted_patch": extracted,
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
        print(json.dumps({"dataset": args.dataset, "index": index + 1, "total": len(prepared), "case": case["case_id"], "status": status}, sort_keys=True), flush=True)
        if time.monotonic() - segment_started >= args.segment_seconds:
            print(json.dumps({"status": "segment_completed", "predictions": len(records)}, sort_keys=True))
            return

    probes = []
    for record, case in zip(records[:config["generation"]["determinism_probe_count"]], prepared, strict=False):
        require(record["status"] == "ok", f"probe source failed: {record['sample_id']}")
        replay = generate_one(model, tokenizer, torch, case["rendered"], generation)
        stable = replay["raw_text"] == record["raw_text"]
        probes.append({"case_id": record["sample_id"], "stable": stable, "first_sha256": "sha256:" + hashlib.sha256(record["raw_text"].encode()).hexdigest(), "replay_sha256": "sha256:" + hashlib.sha256(replay["raw_text"].encode()).hexdigest()})
        require(stable, f"nondeterministic A5 final generation: {record['sample_id']}")
    predictions_path = args.output_dir / "predictions.jsonl"
    require(not predictions_path.exists(), "refusing to overwrite A5 final predictions")
    partial_path.rename(predictions_path)
    write_json(args.output_dir / "determinism-probe.json", probes)
    summary = {
        "version": "a5-dpo-final-generation-v1",
        "dataset": args.dataset,
        "cases": len(records),
        "status_counts": dict(sorted(Counter(row["status"] for row in records).items())),
        "strict_diff_count": sum(row["extracted_patch"] is not None for row in records),
        "input_tokens": sum(row["input_tokens"] for row in records),
        "output_tokens": sum(row["output_tokens"] for row in records),
        "generation_seconds": sum(row["latency_seconds"] for row in records),
        "model_load_seconds_last_segment": load_seconds,
        "peak_gpu_memory_bytes": max(row["max_gpu_memory_bytes"] for row in records),
        "determinism_probe_count": len(probes),
        "determinism_probe_stable": all(row["stable"] for row in probes),
    }
    write_json(args.output_dir / "generation-summary.json", summary)
    run_manifest = {
        "schema_version": "0.1.0",
        "run_id": f"a5_final_{args.dataset}_beta03_s{config['seed']}",
        "stage": "dpo",
        "started_at": state["started_at"],
        "finished_at": utc_now(),
        "git_commit": commit,
        "dirty_worktree": False,
        "config_sha256": sha256_file(args.config),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "model_config_sha256": config["model"]["config_sha256"],
        "adapter_sha256": config["adapter"]["sha256"],
        "dataset_manifest_sha256": dataset["manifest_sha256"],
        "environment_sha256": config["environment"]["lock_sha256"],
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": sha256_file(predictions_path),
        "execution_artifact_sha256": None,
        "notes": f"dataset={args.dataset}; selected=beta03; quantization=nf4; prompts={sha256_file(prompts_path)}; preflight={sha256_file(args.preflight)}",
    }
    Draft202012Validator(read_json(repo / "schemas/run-manifest-v0.1.schema.json"), format_checker=Draft202012Validator.FORMAT_CHECKER).validate(run_manifest)
    write_json(args.output_dir / "run-manifest.json", run_manifest)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
