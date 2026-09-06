"""Frozen input checks and ranking helpers for A4 preference scoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from jsonschema import Draft202012Validator

from scripts.baseline.score_a3_baseline import A31_SCORING_PROTOCOL, load_scoring_protocol
from scripts.preference.build_a4_executable_candidates import MODE
from scripts.training.a3_formal_common import require, sha256_file


VERSION = "a4-preference-scoring-v1"
CHECKPOINT_VERSION = "a4-preference-score-checkpoint-v1"
STATE_VERSION = "a4-preference-scoring-state-v1"
PAIR_VERSION = "0.1.0"
TERMINAL_ORDER = [
    "generation_failed", "parse_failed", "policy_violation", "apply_failed",
    "build_failed", "public_test_failed", "hidden_test_failed",
    "regression_failed", "sanitizer_failed", "success",
]


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def current_commit(repo: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def require_clean(repo: Path) -> None:
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A4 scoring requires a clean worktree")


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong A4 scoring version")
    require(config.get("mode") == MODE, "A4 scoring must remain exploratory")
    require(config["contract"] == {
        "adr": "docs/decisions/0008-a4-execution-ranked-preference-pairs.md",
        "adr_sha256": "sha256:33e45a585817b352fc6137bd267210464d398ecf9f8632aec054a5353259f42e",
        "pair_schema": "schemas/a4-preference-pair-v0.1.schema.json",
        "pair_schema_sha256": "sha256:28db5fae2f759466987fc0630156cb9003c007a070e541ffb4a91dc43724d8e3",
    }, "A4 scoring contract changed")
    source = config["source"]
    expected_source = {
        "generation_directory": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-generation-v1",
        "candidates": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-generation-v1/candidates.jsonl",
        "candidates_sha256": "sha256:ca497dbdd4a989c889d48d2fd9db7b77b4de4d3c327796665a1bde54e7ef0c67",
        "generation_manifest": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-generation-v1/run-manifest.json",
        "generation_manifest_sha256": "sha256:b0a001c3458a16dc07949a60a2b152813c955aa1bc625fe883af6011ca1edef7",
        "generation_summary": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-generation-v1/generation-summary.json",
        "generation_summary_sha256": "sha256:95631a06acdb08106e7fd243c1fd4b910090aa2357435383cdddcf80c85607b2",
        "generation_config": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/generation-config-v1.json",
        "generation_config_sha256": "sha256:45b06c69e3bae492118fdb4002ce1ae5be1bf2831f8232ded1afe8e1b7be5f8d",
        "prompts": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/prompts-v1.jsonl",
        "prompts_sha256": "sha256:a0e8bd0e8f62a9c7530dc942707bd1d19bcc555430dc698e77055a084a1bc273",
        "dataset_directory": "/mingli01/data/patchalign-cpp/a4/executable-source-v1",
        "dataset_manifest": "/mingli01/data/patchalign-cpp/a4/executable-source-v1/preference-source-manifest.json",
        "dataset_manifest_sha256": "sha256:8cba1ec5472a4f4443b766c8fa136f6e928d3911feec9e06457a377775095495",
        "source_generation_git_commit": "a0caffcb2b8796cd0b543c40bc33fce6a6613f06",
    }
    require(source == expected_source, "A4 scoring source identity changed")
    scoring = config["scoring"]
    require(scoring == {
        "protocol": A31_SCORING_PROTOCOL,
        "config": "/mingli01/project/ht/patchalign-cpp/configs/evaluation/a3_scoring_v2.json",
        "config_sha256": "sha256:b8d9507ec7fc97c370e52230759e0b2b84591d6fb4200a50944add19ebe859e8",
        "sandbox": "bubblewrap-rootless-v1",
        "bwrap": "/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap",
        "bwrap_sha256": "sha256:c69d2514ecdcbb927af4129caccceb8bfc122954e59ab8aa6f9ec50e9a09afda",
        "environment_lock": "/mingli01/project/ht/.conda_envs/patchalign-cpp/repro/pip-freeze.txt",
        "environment_sha256": "sha256:bef5b08f129a08a1f720e8698c99606832192d1f77b0f9cce1adc98e3baa43a4",
        "case_count": 264, "candidate_count": 1056, "candidates_per_case": 4,
        "allowed_paths": ["main.cpp"],
        "sanitizer": "not_applicable_for_all_frozen_cases",
    }, "A4 scoring runtime changed")
    require(config["ranking"] == {
        "terminal_order_worst_to_best": TERMINAL_ORDER,
        "timeout_tiebreak": "non_timeout_preferred_within_same_terminal",
        "pair_policy": "one_strongest_contrast_per_case",
        "candidate_index_tiebreak": "lowest_index_for_deterministic_selection_only",
        "require_strictly_better_key": True,
        "maximum_pairs_per_case": 1,
        "uses_gold_patch_similarity": False,
    }, "A4 ranking policy changed")
    require(config["output"] == {
        "directory": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-scoring-v1",
        "checkpoint_directory": "/mingli01/project/ht/patchalign-cpp/artifacts/a4/preference-scoring-v1/checkpoints",
        "preferences": "preferences.jsonl", "pair_audit": "pair-audit.jsonl",
        "scores": "scores.jsonl", "summary": "summary.json", "manifest": "run-manifest.json",
    }, "A4 scoring output paths changed")
    require(config["a5"] == {
        "automatically_authorized": False,
        "decision": "owner_review_required_after_a4_quality_report",
    }, "A5 boundary changed")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify_inputs(config: dict[str, Any], repo: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    validate_config(config)
    contract = config["contract"]
    require(sha256_file(repo / contract["adr"]) == contract["adr_sha256"], "A4 scoring ADR changed")
    require(sha256_file(repo / contract["pair_schema"]) == contract["pair_schema_sha256"], "A4 pair schema changed")
    source = config["source"]
    for path_key, hash_key in (
        ("candidates", "candidates_sha256"),
        ("generation_manifest", "generation_manifest_sha256"),
        ("generation_summary", "generation_summary_sha256"),
        ("generation_config", "generation_config_sha256"),
        ("prompts", "prompts_sha256"),
        ("dataset_manifest", "dataset_manifest_sha256"),
    ):
        require(sha256_file(Path(source[path_key])) == source[hash_key], f"A4 input hash mismatch: {path_key}")
    scoring = config["scoring"]
    require(sha256_file(Path(scoring["config"])) == scoring["config_sha256"], "scoring v2 config changed")
    load_scoring_protocol(Path(scoring["config"]))
    require(sha256_file(Path(scoring["bwrap"])) == scoring["bwrap_sha256"], "Bubblewrap identity changed")
    require(sha256_file(Path(scoring["environment_lock"])) == scoring["environment_sha256"], "environment identity changed")

    generation_manifest = json.loads(Path(source["generation_manifest"]).read_text(encoding="utf-8"))
    require(generation_manifest["git_commit"] == source["source_generation_git_commit"], "generation commit changed")
    require(generation_manifest["candidate_artifact_sha256"] == source["candidates_sha256"], "generation candidate binding changed")
    require(generation_manifest["dataset_manifest_sha256"] == source["dataset_manifest_sha256"], "generation dataset binding changed")
    require(generation_manifest["summary_sha256"] == source["generation_summary_sha256"], "generation summary binding changed")
    require(generation_manifest["config_sha256"] == source["generation_config_sha256"], "generation config binding changed")
    require(generation_manifest["prompts_sha256"] == source["prompts_sha256"], "generation prompts binding changed")
    generation_summary = json.loads(Path(source["generation_summary"]).read_text(encoding="utf-8"))
    require(generation_summary["status_counts"] == {"ok": 1056}, "A4 generation failures changed")
    require(generation_summary["strict_diff_count"] == 1055, "A4 strict diff count changed")
    require(generation_summary["seed_replay_stable"] is True, "A4 seed replay changed")

    manifest = json.loads(Path(source["dataset_manifest"]).read_text(encoding="utf-8"))
    cases = manifest["cases"]
    require(len(cases) == scoring["case_count"], "A4 case denominator changed")
    require(manifest["task_level_counts"] == {"function": 256, "file_window": 8}, "A4 composition changed")
    require(all(item["sanitizer_applicable"] is False and item["sanitizer_status"] == "not_applicable" for item in cases), "A4 sanitizer applicability changed")

    candidates = read_jsonl(Path(source["candidates"]))
    prompts = read_jsonl(Path(source["prompts"]))
    require(len(candidates) == scoring["candidate_count"], "A4 candidate denominator changed")
    require(len(prompts) == scoring["case_count"], "A4 prompt denominator changed")
    candidate_schema = json.loads((repo / "schemas/a4-preference-candidate-v0.1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(candidate_schema)
    for row in candidates:
        validator.validate(row)
    case_ids = [item["case_id"] for item in cases]
    require([row["case_id"] for row in prompts] == case_ids, "A4 prompt order changed")
    expected = [(case_id, index) for case_id in case_ids for index in range(scoring["candidates_per_case"])]
    actual = [(row["case_id"], row["candidate_index"]) for row in candidates]
    require(actual == expected, "A4 candidate order changed")
    require(len({row["candidate_id"] for row in candidates}) == len(candidates), "duplicate A4 candidate")
    prompt_by_case = {row["case_id"]: row for row in prompts}
    item_by_case = {item["case_id"]: item for item in cases}
    for row in candidates:
        prompt = prompt_by_case[row["case_id"]]
        item = item_by_case[row["case_id"]]
        require(row["prompt_sha256"] == prompt["prompt_sha256"], "candidate prompt hash changed")
        require(row["source_train_sample_id"] == item["source_train_sample_id"], "candidate train identity changed")
    return manifest, candidates, prompts


def score_timed_out(score: dict[str, Any]) -> bool:
    return any(
        stage.get("timed_out", False)
        or any(outcome.get("timed_out", False) for outcome in stage.get("outcomes", []))
        for stage in score["stages"].values()
    )


def ranking_key(score: dict[str, Any]) -> tuple[int, int]:
    terminal = score["terminal_classification"]
    require(terminal in TERMINAL_ORDER, f"unknown A4 terminal classification: {terminal}")
    return TERMINAL_ORDER.index(terminal), int(not score_timed_out(score))


def choose_pair(scores: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    require(len(scores) == 4, "A4 pair selection requires four candidates")
    best_key = max(ranking_key(row) for row in scores)
    worst_key = min(ranking_key(row) for row in scores)
    if best_key == worst_key:
        return None
    best = min((row for row in scores if ranking_key(row) == best_key), key=lambda row: row["candidate_index"])
    worst = min((row for row in scores if ranking_key(row) == worst_key), key=lambda row: row["candidate_index"])
    return best, worst
