"""Generate four reproducible M1-R2 candidates per frozen A4 train prompt."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import time
from typing import Any

from jsonschema import Draft202012Validator

from patchalign.evaluation.patches import PatchParseError, parse_unified_diff
from scripts.baseline.run_a3_baseline import load_cases, prompt_sha256, render_model_input
from scripts.preference.build_a4_executable_candidates import MODE
from scripts.preference.finalize_a4_generation_config import ADR_SHA, VERSION
from scripts.preference.qualify_a4_executable_candidates import MANIFEST_NAME, VERSION as SOURCE_VERSION
from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.a3_sft_r2_inference_common import verify_training_artifact
from scripts.training.run_a3_formal_inference import load_model


MODEL_REVISION = "0396a76181e127dfc13e5c5ec48a8cee09938b02"
MODEL_CONFIG_SHA = "sha256:4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605"
ADAPTER_SHA = "sha256:8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def candidate_seed(global_seed: int, case_id: str, candidate_index: int) -> int:
    value = f"{global_seed}\0{case_id}\0{candidate_index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest()[:4], "big") & 0x7FFFFFFF


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong A4 generation version")
    require(config.get("mode") == MODE, "A4 generation is not exploratory")
    require(config["owner_authorization"] == {
        "path": "docs/decisions/0006-owner-authorized-exploratory-a4.md",
        "sha256": ADR_SHA,
        "does_not_change_a3_gate": True,
    }, "A4 owner authorization changed")
    override = config["readiness_override"]
    require(override["a4_ready"] is False, "A4 override must preserve failed readiness")
    require(override["required_blocker"] == "supplementary_confirmation_passed", "A4 confirmation blocker missing")
    require(override["authorization"] == "project_owner_explicit_exploratory_continuation", "A4 override identity changed")
    require(config["model"] == {
        "model_id": "Qwen/Qwen2.5-Coder-7B",
        "local_path": "/mingli01/models/Qwen2.5-Coder-7B",
        "revision": MODEL_REVISION,
        "config_sha256": MODEL_CONFIG_SHA,
    }, "A4 model identity changed")
    require(config["source_training"]["adapter_sha256"] == ADAPTER_SHA, "A4 adapter changed")
    require(config["dataset"]["case_count"] == 264, "A4 case count changed")
    require(config["dataset"]["task_level_counts"] == {"function": 256, "file_window": 8}, "A4 composition changed")
    require(config["prompts"]["count"] == 264, "A4 prompt count changed")
    for key in ("contains_gold_patch", "contains_fixed_code", "contains_hidden_tests", "contains_execution_feedback"):
        require(config["prompts"][key] is False, f"forbidden A4 prompt field: {key}")
    require(config["generation"] == {
        "candidates_per_prompt": 4,
        "do_sample": True,
        "temperature": 0.7,
        "top_p": 0.95,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
        "seed_policy": "sha256(global_seed, case_id, candidate_index)",
    }, "A4 generation policy changed")
    require(config["seed"] == 20260830, "A4 seed changed")
    require(config["output_directory"] == "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-generation-v1", "A4 output changed")


def generate_sample(model: Any, tokenizer: Any, torch: Any, rendered: str, generation: dict[str, Any], seed: int) -> dict[str, Any]:
    random.seed(seed)
    import numpy as np
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=True)
    input_tokens = int(encoded["input_ids"].shape[1])
    require(input_tokens <= generation["max_input_tokens"], "A4 input exceeds token budget")
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.monotonic()
    with torch.inference_mode():
        output = model.generate(
            **encoded,
            do_sample=True,
            temperature=generation["temperature"],
            top_p=generation["top_p"],
            num_return_sequences=1,
            max_new_tokens=generation["max_new_tokens"],
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )
    torch.cuda.synchronize()
    new_ids = output[0, input_tokens:]
    return {
        "raw_text": tokenizer.decode(new_ids, skip_special_tokens=True),
        "input_tokens": input_tokens,
        "output_tokens": int(new_ids.shape[0]),
        "latency_seconds": time.monotonic() - started,
        "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--segment-seconds", type=int, default=27600)
    args = parser.parse_args()
    require(args.segment_seconds >= 600, "A4 segment must be at least 600 seconds")
    repo = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A4 generation requires a clean worktree")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    require(config["git_commit"] == commit, "A4 config/code commit mismatch")
    require(sha256_file(repo / config["owner_authorization"]["path"]) == ADR_SHA, "A4 authorization hash mismatch")
    readiness_path = Path(config["readiness_override"]["path"])
    require(sha256_file(readiness_path) == config["readiness_override"]["sha256"], "A4 readiness ledger changed")
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    require(readiness["a4_ready"] is False and "supplementary_confirmation_passed" in readiness["blockers"], "A4 failed readiness identity changed")
    require(sha256_file(args.environment_lock) == config["environment_sha256"], "A4 environment changed")
    training = verify_training_artifact(config)
    dataset_root = Path(config["dataset"]["root"])
    manifest_path = dataset_root / config["dataset"]["manifest"]
    require(sha256_file(manifest_path) == config["dataset"]["manifest_sha256"], "A4 source manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["version"] == SOURCE_VERSION and manifest["mode"] == MODE, "wrong A4 source manifest")
    prompts_path = Path(config["prompts"]["path"])
    require(sha256_file(prompts_path) == config["prompts"]["sha256"], "A4 prompts changed")
    prompts = [json.loads(line) for line in prompts_path.read_text(encoding="utf-8").splitlines()]
    require(len(prompts) == config["prompts"]["count"], "A4 prompt denominator changed")

    import torch
    from transformers import AutoTokenizer
    require(torch.cuda.is_available() and torch.cuda.device_count() == 1, "A4 requires exactly one visible GPU")
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)
    model_path = Path(config["model"]["local_path"])
    require(sha256_file(model_path / "config.json") == MODEL_CONFIG_SHA, "A4 model config changed")
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    _, cases = load_cases(dataset_root, "main.cpp", MANIFEST_NAME)
    by_id = {case["item"]["case_id"]: case for case in cases}
    require(list(by_id) == [row["case_id"] for row in prompts], "A4 prompt/case order changed")
    prepared = []
    for row in prompts:
        case = by_id[row["case_id"]]
        require(case["item"]["source_train_sample_id"] == row["source_train_sample_id"], "A4 train identity mismatch")
        require(prompt_sha256(case["prompt"]) == row["prompt_sha256"], "A4 prompt reconstruction mismatch")
        require(case["prompt"] == row["prompt_text"], "A4 prompt text mismatch")
        rendered = render_model_input(tokenizer, row["prompt_text"], "raw_completion")
        require(len(tokenizer(rendered, add_special_tokens=True)["input_ids"]) == row["input_tokens"], "A4 token count changed")
        prepared.append((row, rendered))

    output = Path(config["output_directory"])
    state_path = output / "generation-state.json"
    expected_state = {
        "version": "a4-preference-generation-state-v1",
        "mode": MODE,
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "readiness_sha256": config["readiness_override"]["sha256"],
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "prompts_sha256": config["prompts"]["sha256"],
        "adapter_sha256": ADAPTER_SHA,
    }
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for key, value in expected_state.items():
            require(state[key] == value, f"A4 resume mismatch: {key}")
    else:
        require(not output.exists(), "A4 output exists without state")
        output.mkdir(parents=True)
        state = {**expected_state, "started_at": utc_now()}
        write_json(state_path, state)
        shutil.copyfile(prompts_path, output / "prompts.jsonl")

    partial = output / "candidates.partial.jsonl"
    records = [] if not partial.exists() else [json.loads(line) for line in partial.read_text(encoding="utf-8").splitlines()]
    expected_pairs = [(row["case_id"], index) for row, _ in prepared for index in range(config["generation"]["candidates_per_prompt"])]
    require([(row["case_id"], row["candidate_index"]) for row in records] == expected_pairs[:len(records)], "A4 partial order changed")
    validator = Draft202012Validator(json.loads((repo / "schemas/a4-preference-candidate-v0.1.schema.json").read_text(encoding="utf-8")))
    model_started = time.monotonic()
    model = load_model(model_path, "sft", training["adapter_dir"])
    load_seconds = time.monotonic() - model_started
    segment_started = time.monotonic()
    generation = config["generation"]
    run_id = "a4_m1_r2_preference_s20260830"
    for flat_index in range(len(records), len(expected_pairs)):
        case_index, candidate_index = divmod(flat_index, generation["candidates_per_prompt"])
        prompt, rendered = prepared[case_index]
        seed = candidate_seed(config["seed"], prompt["case_id"], candidate_index)
        try:
            result = generate_sample(model, tokenizer, torch, rendered, generation, seed)
            raw_text = result["raw_text"]
            try:
                parse_unified_diff(raw_text)
                extracted, status, error = raw_text, "ok", None
            except PatchParseError:
                extracted, status, error = None, "ok", None
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            result = {"raw_text": "", "input_tokens": prompt["input_tokens"], "output_tokens": 0, "latency_seconds": 0.0, "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated())}
            raw_text, extracted, status, error = "", None, "oom", f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            result = {"raw_text": "", "input_tokens": prompt["input_tokens"], "output_tokens": 0, "latency_seconds": 0.0, "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated())}
            raw_text, extracted, status, error = "", None, "generation_failed", f"{type(exc).__name__}: {exc}"
        record = {
            "schema_version": "0.1.0", "run_id": run_id,
            "candidate_id": f"{prompt['case_id']}:candidate:{candidate_index}",
            "case_id": prompt["case_id"], "source_train_sample_id": prompt["source_train_sample_id"],
            "task_level": prompt["task_level"],
            "model": {"model_id": config["model"]["model_id"], "revision": MODEL_REVISION, "config_sha256": MODEL_CONFIG_SHA, "adapter_sha256": ADAPTER_SHA},
            "prompt_version": prompt["prompt_version"], "prompt_sha256": prompt["prompt_sha256"],
            "seed": seed, "candidate_index": candidate_index,
            "generation": generation, "raw_text": raw_text, "extracted_patch": extracted,
            "status": status, "error": error, "input_tokens": int(result["input_tokens"]),
            "output_tokens": int(result["output_tokens"]), "latency_seconds": float(result["latency_seconds"]),
            "max_gpu_memory_bytes": int(result["max_gpu_memory_bytes"]),
        }
        validator.validate(record)
        with partial.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush(); os.fsync(stream.fileno())
        records.append(record)
        print(json.dumps({"index": flat_index + 1, "total": len(expected_pairs), "candidate_id": record["candidate_id"], "status": status}, sort_keys=True), flush=True)
        if time.monotonic() - segment_started >= args.segment_seconds:
            print(json.dumps({"status": "segment_completed", "candidates": len(records)}, sort_keys=True)); return

    first_prompt, first_rendered = prepared[0]
    probe_seed = candidate_seed(config["seed"], first_prompt["case_id"], 0)
    probe = generate_sample(model, tokenizer, torch, first_rendered, generation, probe_seed)
    stable = probe["raw_text"] == records[0]["raw_text"]
    require(stable, "A4 stochastic seed replay is not deterministic")
    final = output / "candidates.jsonl"
    require(not final.exists(), "refusing to overwrite A4 final candidates")
    partial.rename(final)
    summary = {
        "version": "a4-preference-generation-summary-v1", "mode": MODE,
        "cases": len(prepared), "candidates_per_case": generation["candidates_per_prompt"],
        "candidates": len(records), "status_counts": dict(Counter(row["status"] for row in records)),
        "strict_diff_count": sum(row["extracted_patch"] is not None for row in records),
        "seed_replay_stable": stable, "model_load_seconds_last_segment": load_seconds,
        "generation_seconds": sum(row["latency_seconds"] for row in records),
        "peak_gpu_memory_bytes": max(row["max_gpu_memory_bytes"] for row in records),
    }
    write_json(output / "generation-summary.json", summary)
    write_json(output / "run-manifest.json", {
        "version": "a4-preference-generation-manifest-v1", "mode": MODE,
        "started_at": state["started_at"], "finished_at": utc_now(), "git_commit": commit,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "config_sha256": sha256_file(args.config),
        "readiness_sha256": config["readiness_override"]["sha256"],
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "prompts_sha256": config["prompts"]["sha256"], "adapter_sha256": ADAPTER_SHA,
        "candidate_artifact_sha256": sha256_file(final), "summary_sha256": sha256_file(output / "generation-summary.json"),
    })
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
