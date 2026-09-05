"""Bind qualified train-only cases and failed readiness into exploratory A4 config."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.baseline.run_a3_baseline import load_cases, prompt_sha256, render_model_input
from scripts.preference.build_a4_executable_candidates import MODE, validate_config
from scripts.preference.qualify_a4_executable_candidates import MANIFEST_NAME, VERSION as SOURCE_VERSION
from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.a3_sft_r2_inference_common import verify_training_artifact


VERSION = "a4-preference-generation-v1"
ADR_SHA = "sha256:2b4c1ba07e297b5b58ac3c976527b42af842a05c364e3a3b2e94471f6fcb6d42"
DATA_CONFIG_SHA = "sha256:503c65ffa43035d617bf88b056f75a5be82ca52aaade325a375c4c875b3a683e"
READINESS_PATH = Path("/mingli01/project/ht/patchalign-cpp/artifacts/a3/pre-a4-readiness-v1.json")
OUTPUT_CONFIG = Path("/mingli01/project/ht/patchalign-cpp/artifacts/a4/generation-config-v1.json")
PROMPTS_PATH = Path("/mingli01/project/ht/patchalign-cpp/artifacts/a4/prompts-v1.jsonl")
OUTPUT_DIRECTORY = "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-generation-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-config", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A4 finalization requires a clean worktree")
    require(sha256_file(args.data_config) == DATA_CONFIG_SHA, "A4 data config changed")
    require(sha256_file(repo / "docs/decisions/0006-owner-authorized-exploratory-a4.md") == ADR_SHA, "A4 owner authorization changed")
    config = json.loads(args.data_config.read_text(encoding="utf-8"))
    validate_config(config)
    require(READINESS_PATH.is_file(), "pre-A4 readiness ledger missing")
    readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    require(readiness["version"] == "pre-a4-readiness-v1", "wrong readiness version")
    require(readiness["a4_ready"] is False and readiness["a4_started"] is False, "exploratory override requires failed, unstarted readiness")
    require("supplementary_confirmation_passed" in readiness["blockers"], "confirmation blocker missing")
    require(readiness["observed_gates"]["internal_gate_passed"] is True, "A3.4 internal gate did not pass")

    source_dir = Path(config["paths"]["qualified_directory"])
    source_manifest = source_dir / MANIFEST_NAME
    require(source_manifest.is_file(), "A4 qualified source missing")
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    require(source["version"] == SOURCE_VERSION and source["mode"] == MODE, "wrong A4 source identity")
    require(source["task_level_counts"] == {"function": 256, "file_window": 8}, "A4 source composition changed")
    require(source["leakage_audit"] == {
        "source_split": "train", "validation_records": 0, "internal_records": 0,
        "confirmation_records": 0, "external_records": 0, "problem_family_unique": True,
    }, "A4 source leakage audit failed")

    source_training = json.loads((repo / "configs/evaluation/a3_sft_r2_inference_v1.json").read_text(encoding="utf-8"))["source_training"]
    binding = {"source_training": source_training}
    verify_training_artifact(binding)
    require(args.environment_lock.is_file(), "environment lock missing")
    require(not OUTPUT_CONFIG.exists() and not PROMPTS_PATH.exists(), "refusing to overwrite A4 generation binding")
    require(not Path(OUTPUT_DIRECTORY).exists(), "A4 generation output already exists")

    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, trust_remote_code=False, use_fast=True)
    _, cases = load_cases(source_dir, "main.cpp", MANIFEST_NAME)
    prompt_rows = []
    for case in cases:
        prompt = case["prompt"]
        rendered = render_model_input(tokenizer, prompt, "raw_completion")
        tokens = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
        require(tokens <= 4096, f"A4 prompt too long: {case['item']['case_id']}")
        prompt_rows.append({
            "case_id": case["item"]["case_id"],
            "source_train_sample_id": case["item"]["source_train_sample_id"],
            "task_level": case["item"]["task_level"],
            "prompt_version": "a4-cpp-repair-v1",
            "prompt_sha256": prompt_sha256(prompt),
            "prompt_text": prompt,
            "public_test_id": case["public_test_id"],
            "input_tokens": tokens,
        })
    require(len(prompt_rows) == 264, "wrong A4 prompt count")
    PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPTS_PATH.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in prompt_rows), encoding="utf-8")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    result = {
        "version": VERSION,
        "mode": MODE,
        "created_at": utc_now(),
        "git_commit": commit,
        "owner_authorization": {
            "path": "docs/decisions/0006-owner-authorized-exploratory-a4.md",
            "sha256": ADR_SHA,
            "does_not_change_a3_gate": True,
        },
        "readiness_override": {
            "path": str(READINESS_PATH),
            "sha256": sha256_file(READINESS_PATH),
            "a4_ready": False,
            "required_blocker": "supplementary_confirmation_passed",
            "authorization": "project_owner_explicit_exploratory_continuation",
        },
        "model": {
            "model_id": "Qwen/Qwen2.5-Coder-7B",
            "local_path": str(args.model_path),
            "revision": "0396a76181e127dfc13e5c5ec48a8cee09938b02",
            "config_sha256": sha256_file(args.model_path / "config.json"),
        },
        "source_training": source_training,
        "dataset": {
            "root": str(source_dir),
            "manifest": MANIFEST_NAME,
            "manifest_sha256": sha256_file(source_manifest),
            "case_count": 264,
            "task_level_counts": source["task_level_counts"],
            "source_train_sha256": source["source_train_sha256"],
        },
        "prompts": {
            "path": str(PROMPTS_PATH),
            "sha256": sha256_file(PROMPTS_PATH),
            "count": len(prompt_rows),
            "input_mode": "raw_completion",
            "contains_gold_patch": False,
            "contains_fixed_code": False,
            "contains_hidden_tests": False,
            "contains_execution_feedback": False,
        },
        "generation": {
            "candidates_per_prompt": 4,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.95,
            "max_input_tokens": 4096,
            "max_new_tokens": 512,
            "seed_policy": "sha256(global_seed, case_id, candidate_index)",
        },
        "seed": 20260830,
        "environment_sha256": sha256_file(args.environment_lock),
        "output_directory": OUTPUT_DIRECTORY,
    }
    write_json(OUTPUT_CONFIG, result)
    print(json.dumps({"config": str(OUTPUT_CONFIG), "config_sha256": sha256_file(OUTPUT_CONFIG), "prompts_sha256": result["prompts"]["sha256"], "cases": 264, "candidates": 1056}, sort_keys=True))


if __name__ == "__main__":
    main()
