"""Qualify and freeze the train-only executable source for exploratory A4."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator
from transformers import AutoTokenizer

from scripts.data.a2_output_matcher import matcher_metadata
from scripts.data.a2_sandbox_runtime import SANDBOX_VERSION, resolve_bwrap
from scripts.data.qualify_a3_formal_holdout import (
    evaluate_candidate,
    prompt_token_count,
    qualified_count,
    selectable_count,
    write_json_atomic,
)
from scripts.preference.build_a4_executable_candidates import (
    CANDIDATE_VERSION,
    MODE,
    validate_config,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "a4-executable-preference-source-v1"
PROGRESS_VERSION = "a4-executable-qualification-progress-v1"
MANIFEST_NAME = "preference-source-manifest.json"


def load_cached(progress: Path, items_by_order: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    evaluations: dict[int, dict[str, Any]] = {}
    for path in sorted((progress / "evaluations").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        decision = value["decision"]
        order = decision["candidate_order"]
        require(order in items_by_order, f"unknown A4 candidate checkpoint: {order}")
        source = items_by_order[order]
        for key in ("case_id", "problem_id", "task_level", "candidate_order"):
            require(decision[key] == source[key], f"A4 checkpoint identity mismatch: {key}")
        require(order not in evaluations, f"duplicate A4 checkpoint: {order}")
        evaluations[order] = value
    return evaluations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    paths = config["paths"]
    candidate_dir = Path(paths["candidate_directory"])
    progress = Path(paths["qualification_progress_directory"])
    output = Path(paths["qualified_directory"])
    require(not output.exists(), "refusing to overwrite A4 qualified source")
    manifest_path = candidate_dir / "candidate-manifest.json"
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(candidate["version"] == CANDIDATE_VERSION, "wrong A4 candidate version")
    require(candidate["mode"] == MODE, "A4 candidate is not exploratory")
    require(candidate["source_train_sha256"] == config["source"]["formal_train_sha256"], "A4 train binding changed")
    require(candidate["leakage_audit"] == {
        "source_split": "train",
        "validation_records": 0,
        "internal_records": 0,
        "confirmation_records": 0,
        "external_records": 0,
        "problem_family_unique": True,
    }, "A4 leakage audit failed")
    items = candidate["cases"]
    items_by_order = {item["candidate_order"]: item for item in items}
    require(len(items_by_order) == len(items), "duplicate A4 candidate order")
    required = config["selection"]["required_counts"]
    require(required == {"function": 256, "file_window": 8}, "A4 required composition changed")
    bwrap = resolve_bwrap(args.bwrap)

    identity = {
        "version": PROGRESS_VERSION,
        "source_candidate_version": CANDIDATE_VERSION,
        "source_candidate_manifest_sha256": sha256_file(manifest_path),
        "required_task_levels": required,
        "sandbox_policy_version": SANDBOX_VERSION,
        "output_matcher": matcher_metadata(),
        "mode": MODE,
    }
    progress_manifest = progress / "progress-manifest.json"
    if progress_manifest.exists():
        require(json.loads(progress_manifest.read_text(encoding="utf-8")) == identity, "A4 progress identity changed")
    else:
        unexpected = list(progress.iterdir()) if progress.exists() else []
        require(not unexpected, "A4 progress exists without identity")
        progress.mkdir(parents=True, exist_ok=True)
        write_json_atomic(progress_manifest, identity)

    evaluations = load_cached(progress, items_by_order)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, trust_remote_code=False, use_fast=True)
    max_tokens = config["qualification"]["max_input_tokens"]
    allowed_path = config["qualification"]["allowed_path"]
    prompt_tokens = {
        order: prompt_token_count(candidate_dir, value, tokenizer, allowed_path)
        for order, value in evaluations.items() if value["decision"]["qualified"]
    }
    by_level = {level: [item for item in items if item["task_level"] == level] for level in ("function", "file_window")}
    workers = config["qualification"]["workers"]
    batch_size = config["qualification"]["batch_size"]
    print(json.dumps({"event": "a4_qualification_resume", "cached": len(evaluations), "total": len(items)}, sort_keys=True), flush=True)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for level in ("file_window", "function"):
            level_items = by_level[level]
            while selectable_count(level_items, evaluations, prompt_tokens, max_tokens) < required[level]:
                pending = [item for item in level_items if item["candidate_order"] not in evaluations][:batch_size]
                require(bool(pending), f"A4 candidates cannot fill {level}")
                futures = [executor.submit(evaluate_candidate, (str(candidate_dir), item, str(bwrap))) for item in pending]
                for future in as_completed(futures):
                    value = future.result()
                    order = value["decision"]["candidate_order"]
                    write_json_atomic(progress / "evaluations" / f"{order:04d}.json", value)
                    evaluations[order] = value
                    if value["decision"]["qualified"]:
                        prompt_tokens[order] = prompt_token_count(candidate_dir, value, tokenizer, allowed_path)
                print(json.dumps({
                    "event": "a4_qualification_batch",
                    "task_level": level,
                    "evaluated": len(evaluations),
                    "qualified": qualified_count(level_items, evaluations),
                    "selectable": selectable_count(level_items, evaluations, prompt_tokens, max_tokens),
                    "required": required[level],
                }, sort_keys=True), flush=True)

    selected_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for order in sorted(evaluations):
        evaluation = evaluations[order]
        decision = dict(evaluation["decision"])
        level = decision["task_level"]
        if decision["qualified"]:
            decision["prompt_tokens"] = prompt_tokens[order]
            if prompt_tokens[order] > max_tokens:
                decision["qualified"] = False
                decision["reasons"] = [*decision["reasons"], "prompt_tokens_over_limit"]
        decision["selected"] = bool(decision["qualified"] and selected_counts[level] < required[level])
        if decision["selected"]:
            selected.append(evaluation)
            selected_counts[level] += 1
        else:
            rejection_counts.update(decision["reasons"])
        decisions.append(decision)
    require(dict(selected_counts) == required, f"A4 qualified composition incomplete: {dict(selected_counts)}")

    schema = Path(__file__).resolve().parents[2] / "schemas" / "a2-execution-v0.2.schema.json"
    validator = Draft202012Validator(json.loads(schema.read_text(encoding="utf-8")))
    for evaluation in selected:
        validator.validate(evaluation["case_result"])

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="a4-executable-source-building-", dir=output.parent))
    try:
        (temporary / "cases").mkdir()
        selected_manifest = []
        selected_results = []
        for evaluation in selected:
            item = evaluation["selected_item"]
            shutil.copytree(candidate_dir / "cases" / item["case_id"], temporary / "cases" / item["case_id"])
            write_json(temporary / "cases" / item["case_id"] / "test-partition.json", evaluation["partitions"])
            selected_manifest.append(item)
            selected_results.append(evaluation["case_result"])
        manifest = {
            "version": VERSION,
            "mode": MODE,
            "source_candidate_manifest_sha256": sha256_file(manifest_path),
            "source_train_sha256": config["source"]["formal_train_sha256"],
            "task_level_counts": dict(selected_counts),
            "partition_rule": "F=buggy-fail/fixed-pass; public=stable first ceil(20%) of F; hidden=remaining F; regression=buggy-pass/fixed-pass",
            "output_matcher": matcher_metadata(),
            "prompt_token_policy": {
                "model_config_sha256": sha256_file(args.model_path / "config.json"),
                "input_mode": "raw_completion",
                "allowed_path": allowed_path,
                "max_input_tokens": max_tokens,
            },
            "leakage_audit": candidate["leakage_audit"],
            "cases": selected_manifest,
        }
        report = {
            "version": VERSION,
            "mode": MODE,
            "selected_count": len(selected_manifest),
            "selected_task_levels": dict(selected_counts),
            "evaluated_candidates": len(decisions),
            "unevaluated_candidates": len(items) - len(decisions),
            "qualified_candidates": sum(decision["qualified"] for decision in decisions),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "progress_version": PROGRESS_VERSION,
            "decisions": decisions,
        }
        write_json(temporary / MANIFEST_NAME, manifest)
        write_json(temporary / "qualification-report.json", report)
        (temporary / "qualification-results.jsonl").write_text("".join(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n" for result in selected_results), encoding="utf-8")
        artifacts = [temporary / MANIFEST_NAME, temporary / "qualification-report.json", temporary / "qualification-results.jsonl", *sorted((temporary / "cases").glob("*/*"))]
        (temporary / "sha256sums.txt").write_text("".join(f"{sha256_file(path)[7:]}  {path.relative_to(temporary)}\n" for path in artifacts), encoding="utf-8")
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"output": str(output), "selected": len(selected), "counts": dict(selected_counts), "manifest_sha256": sha256_file(output / MANIFEST_NAME)}, sort_keys=True))


if __name__ == "__main__":
    main()
