"""Aggregate A4 candidate scores and build conservative execution-ranked pairs."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from jsonschema import Draft202012Validator

from scripts.baseline.score_a3_baseline import summarize
from scripts.preference.a4_score_common import CHECKPOINT_VERSION, PAIR_VERSION, TERMINAL_ORDER, choose_pair, current_commit, ranking_key, require_clean, score_timed_out, sha256_text, verify_inputs
from scripts.training.a3_formal_common import require, sha256_file


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_atomic(path: Path, value: str) -> None:
    if path.exists():
        require(path.read_text(encoding="utf-8") == value, f"A4 final artifact differs on resume: {path.name}")
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", delete=False) as stream:
        stream.write(value)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def jsonl_text(values: list[object]) -> str:
    return "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require_clean(repo)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    manifest, candidates, prompts = verify_inputs(config, repo)
    output = Path(config["output"]["directory"])
    state = json.loads((output / "scoring-state.json").read_text(encoding="utf-8"))
    commit = current_commit(repo)
    config_sha = sha256_file(args.config)
    require(state["scorer_git_commit"] == commit and state["config_sha256"] == config_sha, "A4 finalizer identity changed")
    checkpoint_paths = sorted((output / "checkpoints").glob("*.json"))
    require(len(checkpoint_paths) == config["scoring"]["case_count"], "A4 checkpoint denominator incomplete")
    all_scores = []
    grouped_scores = []
    for index, (item, path) in enumerate(zip(manifest["cases"], checkpoint_paths)):
        require(path.name == f"{index:04d}.json", "A4 checkpoint index changed")
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        require(checkpoint["version"] == CHECKPOINT_VERSION, "wrong A4 checkpoint version")
        require(checkpoint["config_sha256"] == config_sha and checkpoint["scorer_git_commit"] == commit, "A4 checkpoint binding changed")
        require(checkpoint["case_index"] == index and checkpoint["case_id"] == item["case_id"], "A4 checkpoint case changed")
        scores = checkpoint["scores"]
        expected_candidates = candidates[index * 4:(index + 1) * 4]
        require(len(scores) == 4 and [row["candidate_index"] for row in scores] == [0, 1, 2, 3], "A4 checkpoint candidate order changed")
        require(all(row["case_id"] == item["case_id"] for row in scores), "A4 score case identity changed")
        for score, candidate in zip(scores, expected_candidates):
            require(score["candidate_id"] == candidate["candidate_id"], "A4 checkpoint candidate identity changed")
            require(score["prediction_sha256"] == sha256_text(candidate["raw_text"]), "A4 checkpoint prediction binding changed")
            require(score["candidate_record_sha256"] == sha256_text(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), "A4 checkpoint source-record binding changed")
            require(score.get("scoring_protocol_version") == config["scoring"]["protocol"], "A4 checkpoint scoring protocol changed")
        grouped_scores.append(scores)
        all_scores.extend(scores)
    require(len(all_scores) == 1056 and len({row["candidate_id"] for row in all_scores}) == 1056, "A4 score denominator changed")

    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    prompt_by_case = {row["case_id"]: row for row in prompts}
    pair_schema_path = repo / "schemas/a4-preference-pair-v0.1.schema.json"
    pair_validator = Draft202012Validator(json.loads(pair_schema_path.read_text(encoding="utf-8")))
    preferences = []
    audits = []
    no_pair = []
    for item, scores in zip(manifest["cases"], grouped_scores):
        selected = choose_pair(scores)
        if selected is None:
            no_pair.append(item["case_id"])
            continue
        chosen_score, rejected_score = selected
        chosen = candidate_by_id[chosen_score["candidate_id"]]
        rejected = candidate_by_id[rejected_score["candidate_id"]]
        prompt = prompt_by_case[item["case_id"]]
        require(chosen["raw_text"] != rejected["raw_text"], "A4 preferred responses are identical")
        pair_digest = hashlib.sha256(f"{item['case_id']}\0{chosen['candidate_id']}\0{rejected['candidate_id']}".encode()).hexdigest()
        pair_id = f"a4-pair-{pair_digest[:20]}"
        preference = {
            "schema_version": PAIR_VERSION,
            "pair_id": pair_id,
            "case_id": item["case_id"],
            "source_train_sample_id": item["source_train_sample_id"],
            "task_level": item["task_level"],
            "prompt_version": prompt["prompt_version"],
            "prompt_sha256": prompt["prompt_sha256"],
            "prompt": prompt["prompt_text"],
            "chosen": {
                "candidate_id": chosen["candidate_id"], "candidate_index": chosen["candidate_index"],
                "response_sha256": sha256_text(chosen["raw_text"]), "response": chosen["raw_text"],
            },
            "rejected": {
                "candidate_id": rejected["candidate_id"], "candidate_index": rejected["candidate_index"],
                "response_sha256": sha256_text(rejected["raw_text"]), "response": rejected["raw_text"],
            },
        }
        pair_validator.validate(preference)
        chosen_key, rejected_key = ranking_key(chosen_score), ranking_key(rejected_score)
        require(chosen_key > rejected_key, "A4 pair is not strictly ordered")
        reason = "terminal_stage" if chosen_key[0] != rejected_key[0] else "timeout_tiebreak"
        audits.append({
            "pair_id": pair_id, "case_id": item["case_id"], "task_level": item["task_level"],
            "chosen_candidate_id": chosen["candidate_id"], "chosen_terminal": chosen_score["terminal_classification"],
            "chosen_timed_out": score_timed_out(chosen_score), "chosen_rank": list(chosen_key),
            "rejected_candidate_id": rejected["candidate_id"], "rejected_terminal": rejected_score["terminal_classification"],
            "rejected_timed_out": score_timed_out(rejected_score), "rejected_rank": list(rejected_key),
            "reason": reason,
        })
        preferences.append(preference)

    execution = summarize(all_scores)
    summary = {
        "version": "a4-preference-scoring-summary-v1",
        "mode": config["mode"],
        "candidate_count": len(all_scores),
        "case_count": len(grouped_scores),
        "pair_count": len(preferences),
        "no_pair_case_count": len(no_pair),
        "pair_task_levels": dict(sorted(Counter(row["task_level"] for row in preferences).items())),
        "chosen_terminals": dict(sorted(Counter(row["chosen_terminal"] for row in audits).items())),
        "rejected_terminals": dict(sorted(Counter(row["rejected_terminal"] for row in audits).items())),
        "pair_reasons": dict(sorted(Counter(row["reason"] for row in audits).items())),
        "chosen_success_pairs": sum(row["chosen_terminal"] == "success" for row in audits),
        "execution": execution,
        "ranking_terminal_order_worst_to_best": TERMINAL_ORDER,
        "a5_automatically_authorized": False,
        "a5_decision": "owner_review_required_after_a4_quality_report",
    }
    scores_path = output / config["output"]["scores"]
    preferences_path = output / config["output"]["preferences"]
    audit_path = output / config["output"]["pair_audit"]
    summary_path = output / config["output"]["summary"]
    write_atomic(scores_path, jsonl_text(all_scores))
    write_atomic(preferences_path, jsonl_text(preferences))
    write_atomic(audit_path, jsonl_text(audits))
    write_atomic(summary_path, json_text(summary))
    run_manifest = {
        "version": "a4-preference-scoring-manifest-v1",
        "mode": config["mode"],
        "finished_at": utc_now(),
        "scorer_git_commit": commit,
        "source_generation_git_commit": config["source"]["source_generation_git_commit"],
        "config_sha256": config_sha,
        "contract_adr_sha256": config["contract"]["adr_sha256"],
        "candidate_artifact_sha256": config["source"]["candidates_sha256"],
        "dataset_manifest_sha256": config["source"]["dataset_manifest_sha256"],
        "scores_sha256": sha256_file(scores_path),
        "summary_sha256": sha256_file(summary_path),
        "preferences_sha256": sha256_file(preferences_path),
        "pair_audit_sha256": sha256_file(audit_path),
        "pair_schema_sha256": sha256_file(pair_schema_path),
        "candidate_count": len(all_scores),
        "pair_count": len(preferences),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "a5_started": False,
    }
    manifest_path = output / config["output"]["manifest"]
    write_atomic(manifest_path, json_text(run_manifest))
    print(json.dumps({"output": str(output), "candidates": len(all_scores), "pairs": len(preferences), "chosen_success_pairs": summary["chosen_success_pairs"], "manifest_sha256": sha256_file(manifest_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
