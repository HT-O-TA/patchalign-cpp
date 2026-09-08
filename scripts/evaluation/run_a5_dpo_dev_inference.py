#!/usr/bin/env python3
"""Deterministic adapter inference on the frozen 64-case A5 development set."""

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
from scripts.evaluation.a5_dpo_dev_common import ROLES, read_json, resolve_adapter, validate_config, verify_dataset
from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.run_a3_formal_inference import load_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 dev inference requires a clean worktree")
    expected_output = Path(config["outputs"]["inference_root"]) / args.role
    require(args.output_dir == expected_output, "unexpected A5 dev inference output")
    require(not args.output_dir.exists(), "refusing to overwrite A5 dev inference")
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    preflight_path = Path(config["outputs"]["preflight"])
    preflight = read_json(preflight_path)
    require(preflight["version"] == "a5-dpo-dev-preflight-v1" and preflight["status"] == "passed", "A5 dev preflight not passed")
    require(preflight["git_commit"] == commit, "A5 dev preflight commit mismatch")
    require(preflight["config_sha256"] == sha256_file(args.config), "A5 dev preflight config mismatch")
    model_identity = resolve_adapter(config, args.role)
    require(preflight["models"][args.role] == model_identity, "A5 dev model identity changed after preflight")
    root, _ = verify_dataset(config)

    import numpy as np
    import torch
    from transformers import AutoTokenizer

    require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "exactly one CUDA GPU required")
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
    _, cases = load_cases(root, config["inference"]["allowed_path"], config["dataset"]["manifest"])
    prompts = [json.loads(line) for line in Path(config["outputs"]["prompts"]).read_text(encoding="utf-8").splitlines()]
    require(sha256_file(Path(config["outputs"]["prompts"])) == preflight["prompts_sha256"], "A5 dev prompts changed")
    require([row["case_id"] for row in prompts] == [case["item"]["case_id"] for case in cases], "A5 dev prompt order changed")
    prepared = []
    for case, prompt in zip(cases, prompts, strict=True):
        require(prompt["prompt_text"] == case["prompt"], "A5 dev prompt reconstruction changed")
        require(prompt["prompt_sha256"] == prompt_sha256(case["prompt"]), "A5 dev prompt hash changed")
        rendered = render_model_input(tokenizer, case["prompt"], config["inference"]["input_mode"])
        require(len(tokenizer(rendered, add_special_tokens=True)["input_ids"]) == prompt["input_tokens"], "A5 dev token count changed")
        prepared.append({**case, "rendered": rendered, "input_tokens": prompt["input_tokens"]})

    args.output_dir.mkdir(parents=True)
    state = {
        "version": "a5-dpo-dev-inference-state-v1",
        "role": args.role,
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "preflight_sha256": sha256_file(preflight_path),
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "adapter_sha256": model_identity["adapter_sha256"],
        "started_at": started_at,
    }
    write_json(args.output_dir / "inference-state.json", state)
    load_started = time.monotonic()
    model = load_model(Path(config["model"]["local_path"]), "sft", Path(model_identity["adapter_path"]))
    load_seconds = time.monotonic() - load_started
    generation = {key: config["inference"][key] for key in (
        "do_sample", "temperature", "top_p", "num_return_sequences",
        "max_input_tokens", "max_new_tokens",
    )}
    schema = json.loads((repo / "schemas/prediction-v0.1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    records = []
    predictions_path = args.output_dir / "predictions.jsonl"
    with predictions_path.open("x", encoding="utf-8") as stream:
        for index, case in enumerate(prepared):
            item = case["item"]
            try:
                result = generate_one(model, tokenizer, torch, case["rendered"], generation)
                raw_text = result["raw_text"]
                try:
                    parse_unified_diff(raw_text)
                    extracted = raw_text
                except PatchParseError:
                    extracted = None
                status, error = "ok", None
            except torch.cuda.OutOfMemoryError as exc:
                torch.cuda.empty_cache()
                result = {"raw_text": "", "input_tokens": case["input_tokens"], "output_tokens": 0, "latency_seconds": 0.0, "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated())}
                extracted, status, error = None, "oom", f"{type(exc).__name__}: {exc}"
            except Exception as exc:
                result = {"raw_text": "", "input_tokens": case["input_tokens"], "output_tokens": 0, "latency_seconds": 0.0, "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated())}
                extracted, status, error = None, "generation_failed", f"{type(exc).__name__}: {exc}"
            record = {
                "schema_version": "0.1.0",
                "run_id": f"a5_dev_{args.role}_s{config['seed']}",
                "sample_id": item["case_id"],
                "model": {
                    "model_id": config["model"]["model_id"],
                    "revision": config["model"]["revision"],
                    "config_sha256": config["model"]["config_sha256"],
                    "adapter_sha256": model_identity["adapter_sha256"],
                },
                "prompt_version": config["inference"]["prompt_version"],
                "prompt_sha256": prompt_sha256(case["prompt"]),
                "seed": config["seed"],
                "generation": generation,
                "raw_text": result["raw_text"],
                "extracted_patch": extracted,
                "status": status,
                "error": error,
                "input_tokens": int(result["input_tokens"]),
                "output_tokens": int(result["output_tokens"]),
                "latency_seconds": float(result["latency_seconds"]),
                "max_gpu_memory_bytes": int(result["max_gpu_memory_bytes"]),
            }
            validator.validate(record)
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            records.append(record)
            print(json.dumps({"role": args.role, "index": index + 1, "total": len(prepared), "status": status}, sort_keys=True), flush=True)

    probes = []
    for record, case in zip(records[: config["inference"]["determinism_probe_count"]], prepared, strict=False):
        require(record["status"] == "ok", "determinism probe source failed")
        replay = generate_one(model, tokenizer, torch, case["rendered"], generation)
        stable = replay["raw_text"] == record["raw_text"]
        probes.append({
            "case_id": record["sample_id"], "stable": stable,
            "first_sha256": "sha256:" + hashlib.sha256(record["raw_text"].encode()).hexdigest(),
            "replay_sha256": "sha256:" + hashlib.sha256(replay["raw_text"].encode()).hexdigest(),
        })
        require(stable, "nondeterministic A5 dev generation")
    write_json(args.output_dir / "determinism-probe.json", probes)
    summary = {
        "version": "a5-dpo-dev-generation-v1",
        "role": args.role,
        "cases": len(records),
        "status_counts": dict(sorted(Counter(row["status"] for row in records).items())),
        "strict_diff_count": sum(row["extracted_patch"] is not None for row in records),
        "input_tokens": sum(row["input_tokens"] for row in records),
        "output_tokens": sum(row["output_tokens"] for row in records),
        "generation_seconds": sum(row["latency_seconds"] for row in records),
        "model_load_seconds": load_seconds,
        "peak_gpu_memory_bytes": max(row["max_gpu_memory_bytes"] for row in records),
        "determinism_probe_count": len(probes),
        "determinism_probe_stable": all(row["stable"] for row in probes),
    }
    write_json(args.output_dir / "generation-summary.json", summary)
    manifest = {
        "schema_version": "0.1.0",
        "run_id": f"a5_dev_{args.role}_s{config['seed']}",
        "stage": model_identity["stage"],
        "started_at": None,
        "finished_at": None,
        "git_commit": commit,
        "dirty_worktree": False,
        "config_sha256": sha256_file(args.config),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "model_config_sha256": config["model"]["config_sha256"],
        "adapter_sha256": model_identity["adapter_sha256"],
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "environment_sha256": config["environment"]["lock_sha256"],
        "seed": config["seed"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": sha256_file(predictions_path),
        "execution_artifact_sha256": None,
        "notes": f"role={args.role}; quantization=nf4; prompts={preflight['prompts_sha256']}; preflight={sha256_file(preflight_path)}",
    }
    manifest["started_at"] = state["started_at"]
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    Draft202012Validator(json.loads((repo / "schemas/run-manifest-v0.1.schema.json").read_text(encoding="utf-8"))).validate(manifest)
    write_json(args.output_dir / "run-manifest.json", manifest)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
