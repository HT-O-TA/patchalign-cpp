#!/usr/bin/env python3
"""Audit and freeze the resume-delivery DPO preference set from immutable A4 evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from jsonschema import Draft202012Validator

from scripts.preference.a4_score_common import TERMINAL_ORDER, ranking_key, sha256_text
from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "resume-dpo-preference-audit-v1"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def pair_decision(audit: dict[str, Any]) -> tuple[bool, str]:
    if audit["reason"] == "timeout_tiebreak":
        return False, "timeout_tiebreak_excluded"
    require(audit["reason"] == "terminal_stage", "unknown A4 pair reason")
    require(tuple(audit["chosen_rank"]) > tuple(audit["rejected_rank"]), "pair is not strictly ranked")
    return True, "terminal_stage_strictly_better"


def validate_config(repo: Path, config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected DPO preference audit version")
    for name, spec in config["inputs"].items():
        path = repo / spec["path"] if not Path(spec["path"]).is_absolute() else Path(spec["path"])
        require(path.is_file(), f"missing input: {name}")
        require(sha256_file(path) == spec["sha256"], f"input hash changed: {name}")
    policy = config["policy"]
    require(policy == {
        "source_pair_count": 182,
        "exclude_pair_reasons": ["timeout_tiebreak"],
        "expected_excluded_count": 7,
        "minimum_approved_pairs": 150,
        "minimum_chosen_success_pairs": 70,
        "maximum_pairs_per_case": 1,
        "gold_or_test_content_in_training": False,
    }, "DPO preference policy changed")
    require(config["boundaries"] == {
        "source_split": "train",
        "dev_exec_overlap": 0,
        "formal_overlap": 0,
        "confirmation_overlap": 0,
        "external_overlap": 0,
        "evaluation_gold_consumed": False,
        "overwrite_allowed": False,
    }, "DPO preference boundary changed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    inputs = config["inputs"]

    def input_path(name: str) -> Path:
        path = Path(inputs[name]["path"])
        return path if path.is_absolute() else repo / path

    source_manifest = read_json(input_path("a4_source_manifest"))
    dev_manifest = read_json(input_path("dev_exec_manifest"))
    source_run = read_json(input_path("a4_run_manifest"))
    source_summary = read_json(input_path("a4_summary"))
    preferences = read_jsonl(input_path("a4_preferences"))
    audits = read_jsonl(input_path("a4_pair_audit"))
    scores = read_jsonl(input_path("a4_scores"))
    schema = read_json(input_path("pair_schema"))
    validator = Draft202012Validator(schema)

    require(source_run["preferences_sha256"] == inputs["a4_preferences"]["sha256"], "A4 preference binding changed")
    require(source_run["pair_audit_sha256"] == inputs["a4_pair_audit"]["sha256"], "A4 pair-audit binding changed")
    require(source_run["scores_sha256"] == inputs["a4_scores"]["sha256"], "A4 scores binding changed")
    require(source_run["summary_sha256"] == inputs["a4_summary"]["sha256"], "A4 summary binding changed")
    require(source_run["dataset_manifest_sha256"] == inputs["a4_source_manifest"]["sha256"], "A4 dataset binding changed")
    require(source_run["pair_schema_sha256"] == inputs["pair_schema"]["sha256"], "A4 schema binding changed")
    require(len(preferences) == len(audits) == config["policy"]["source_pair_count"], "source pair denominator changed")
    require(len(scores) == source_summary["candidate_count"] == 1056, "source score denominator changed")
    require(source_summary["pair_count"] == len(preferences), "source summary pair count changed")

    a4_cases = {row["case_id"]: row for row in source_manifest["cases"]}
    require(len(a4_cases) == 264, "A4 case denominator changed")
    require(all(row["upstream_split"] == "train" for row in a4_cases.values()), "non-train A4 case")
    require(source_manifest["leakage_audit"] == {
        "source_split": "train", "validation_records": 0, "internal_records": 0,
        "confirmation_records": 0, "external_records": 0, "problem_family_unique": True,
    }, "A4 leakage audit changed")
    dev_case_ids = {row["case_id"] for row in dev_manifest["cases"]}
    dev_problem_ids = {str(row["problem_id"]) for row in dev_manifest["cases"]}
    require(len(dev_case_ids) == dev_manifest["selected_count"], "dev case identity collision")
    require(not dev_case_ids & set(a4_cases), "DPO/dev case overlap")
    require(not dev_problem_ids & {str(row["problem_id"]) for row in a4_cases.values()}, "DPO/dev family overlap")
    require(dev_manifest["a4_selected_overlap"] == 0 and dev_manifest["problem_family_unique"] is True, "dev isolation changed")

    score_by_id = {row["candidate_id"]: row for row in scores}
    audit_by_id = {row["pair_id"]: row for row in audits}
    require(len(score_by_id) == len(scores), "duplicate candidate score")
    require(len(audit_by_id) == len(audits), "duplicate pair audit")
    approved: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for pair in preferences:
        validator.validate(pair)
        pair_id = pair["pair_id"]
        require(pair_id in audit_by_id, f"missing pair audit: {pair_id}")
        audit = audit_by_id[pair_id]
        require(pair["case_id"] == audit["case_id"], "pair/audit case mismatch")
        require(pair["case_id"] in a4_cases, "pair case outside A4 train source")
        case = a4_cases[pair["case_id"]]
        require(pair["source_train_sample_id"] == case["source_train_sample_id"], "train identity mismatch")
        require(pair["task_level"] == case["task_level"] == audit["task_level"], "task level mismatch")
        require(sha256_text(pair["prompt"]) == pair["prompt_sha256"], "prompt hash mismatch")
        chosen = pair["chosen"]
        rejected = pair["rejected"]
        require(chosen["candidate_id"] == audit["chosen_candidate_id"], "chosen audit mismatch")
        require(rejected["candidate_id"] == audit["rejected_candidate_id"], "rejected audit mismatch")
        require(chosen["response"] != rejected["response"], "identical preference responses")
        require(sha256_text(chosen["response"]) == chosen["response_sha256"], "chosen response hash mismatch")
        require(sha256_text(rejected["response"]) == rejected["response_sha256"], "rejected response hash mismatch")
        chosen_score = score_by_id[chosen["candidate_id"]]
        rejected_score = score_by_id[rejected["candidate_id"]]
        for score in (chosen_score, rejected_score):
            require(score["case_id"] == pair["case_id"], "candidate score case mismatch")
            require(score["source_train_sample_id"] == pair["source_train_sample_id"], "candidate score train mismatch")
        require(chosen_score["prediction_sha256"] == chosen["response_sha256"], "chosen score hash mismatch")
        require(rejected_score["prediction_sha256"] == rejected["response_sha256"], "rejected score hash mismatch")
        require(chosen_score["terminal_classification"] == audit["chosen_terminal"], "chosen terminal mismatch")
        require(rejected_score["terminal_classification"] == audit["rejected_terminal"], "rejected terminal mismatch")
        require(list(ranking_key(chosen_score)) == audit["chosen_rank"], "chosen rank mismatch")
        require(list(ranking_key(rejected_score)) == audit["rejected_rank"], "rejected rank mismatch")
        include, reason = pair_decision(audit)
        decisions.append({
            "pair_id": pair_id, "case_id": pair["case_id"], "included": include,
            "decision_reason": reason, "chosen_terminal": audit["chosen_terminal"],
            "rejected_terminal": audit["rejected_terminal"], "task_level": pair["task_level"],
        })
        if include:
            approved.append(pair)

    policy = config["policy"]
    excluded = [row for row in decisions if not row["included"]]
    require(len(excluded) == policy["expected_excluded_count"], "excluded count changed")
    require(len({row["case_id"] for row in approved}) == len(approved), "more than one pair per case")
    chosen_success = sum(row["chosen_terminal"] == "success" and row["included"] for row in decisions)
    resume_gate = len(approved) >= policy["minimum_approved_pairs"] and chosen_success >= policy["minimum_chosen_success_pairs"]
    require(resume_gate, "resume DPO preference gate failed")

    output = Path(config["output_directory"])
    require(not output.exists(), "refusing to overwrite DPO preference output")
    output.mkdir(parents=True)
    (output / "preferences.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in approved), encoding="utf-8", newline="\n")
    (output / "audit.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in decisions), encoding="utf-8", newline="\n")
    summary = {
        "version": VERSION,
        "source_pairs": len(preferences),
        "approved_pairs": len(approved),
        "excluded_pairs": len(excluded),
        "exclusion_reasons": dict(sorted(Counter(row["decision_reason"] for row in excluded).items())),
        "task_levels": dict(sorted(Counter(row["task_level"] for row in approved).items())),
        "chosen_terminals": dict(sorted(Counter(row["chosen_terminal"] for row in decisions if row["included"]).items())),
        "rejected_terminals": dict(sorted(Counter(row["rejected_terminal"] for row in decisions if row["included"]).items())),
        "chosen_success_pairs": chosen_success,
        "research_gate_300_150_passed": len(approved) >= 300 and chosen_success >= 150,
        "resume_gate": {"minimum_pairs": 150, "minimum_chosen_success": 70, "passed": resume_gate},
        "terminal_order_worst_to_best": TERMINAL_ORDER,
        "dev_exec_overlap": 0,
        "evaluation_overlap": 0,
        "gold_or_test_content_in_training": False,
    }
    write_json(output / "summary.json", summary)
    manifest = {
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", "local"),
        "config_sha256": sha256_file(args.config),
        "input_sha256": {name: spec["sha256"] for name, spec in inputs.items()},
        "output_sha256": {
            "preferences.jsonl": sha256_file(output / "preferences.jsonl"),
            "audit.jsonl": sha256_file(output / "audit.jsonl"),
            "summary.json": sha256_file(output / "summary.json"),
        },
        "approved_pairs": len(approved),
        "chosen_success_pairs": chosen_success,
        "resume_gate_passed": resume_gate,
        "research_gate_300_150_passed": False,
    }
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps({"output": str(output), "approved": len(approved), "chosen_success": chosen_success, "research_gate": False, "resume_gate": resume_gate, "manifest_sha256": sha256_file(output / "run-manifest.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
