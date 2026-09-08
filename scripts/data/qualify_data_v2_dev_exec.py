#!/usr/bin/env python3
"""Extend frozen A4 train-only qualification into an independent Data-v2 dev set."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from transformers import AutoTokenizer

from scripts.data.a2_sandbox_runtime import resolve_bwrap
from scripts.data.qualify_a3_formal_holdout import evaluate_candidate, prompt_token_count, write_json_atomic
from scripts.preference.qualify_a4_executable_candidates import load_cached
from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "data-v2-dev-exec-v1"
PROGRESS_VERSION = "data-v2-dev-exec-progress-v1"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_config(repo: Path, config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected dev-exec version")
    decision = config["decision"]
    require(sha256_file(repo / decision["path"]) == decision["sha256"], "decision hash changed")
    selection = config["selection"]
    require(selection == {
        "split": "train",
        "source_dataset": "RunBugRun",
        "task_level": "function",
        "target_count": 64,
        "minimum_count": 50,
        "order": "ascending frozen A4 candidate_order after excluding all A4 selected cases",
        "model_output_or_score_used": False,
    }, "selection contract changed")
    require(config["qualification"]["double_replay_required"] is True, "double replay disabled")
    require(config["qualification"]["max_input_tokens"] == 4096, "token limit changed")
    require(config["boundaries"] == {
        "a4_selected_cases_reused": False,
        "evaluation_content_read": False,
        "evaluation_gold_consumed": False,
        "training_data_created": False,
        "gpu_authorized": False,
        "overwrite_allowed": False,
    }, "safety boundary changed")


def qualified_with_tokens(
    evaluation: dict[str, Any], candidate_dir: Path, tokenizer: Any, max_tokens: int, allowed_path: str
) -> tuple[bool, int | None]:
    if not evaluation["decision"]["qualified"]:
        return False, None
    tokens = prompt_token_count(candidate_dir, evaluation, tokenizer, allowed_path)
    return tokens <= max_tokens, tokens


def a4_selected_orders(cases: list[dict[str, Any]]) -> set[int]:
    orders = {int(case["source_candidate_order"]) for case in cases}
    require(len(orders) == len(cases), "A4 selected source order collision")
    return orders


def eligible_orders(
    items: list[dict[str, Any]], selected_orders: set[int]
) -> list[int]:
    return sorted(
        int(item["candidate_order"])
        for item in items
        if item["candidate_order"] not in selected_orders
        and item["source_dataset"] == "RunBugRun"
        and item["upstream_split"] == "train"
        and item["task_level"] == "function"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(repo, config)
    source = config["source"]
    candidate_dir = Path(source["candidate_directory"])
    candidate_manifest_path = candidate_dir / "candidate-manifest.json"
    require(sha256_file(candidate_manifest_path) == source["candidate_manifest_sha256"], "candidate manifest changed")
    candidate = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    require(candidate["source_train_sha256"] == source["formal_train_sha256"], "formal train binding changed")
    require(candidate["leakage_audit"]["problem_family_unique"] is True, "candidate family uniqueness changed")

    a4_path = Path(source["a4_selected_manifest"])
    require(sha256_file(a4_path) == source["a4_selected_manifest_sha256"], "A4 selected manifest changed")
    a4 = json.loads(a4_path.read_text(encoding="utf-8"))
    require(len(a4["cases"]) == 264, "A4 selected denominator changed")
    selected_orders = a4_selected_orders(a4["cases"])
    selected_case_ids = {str(item["case_id"]) for item in a4["cases"]}
    require(len(selected_orders) == len(selected_case_ids) == 264, "A4 selected identity collision")

    items = candidate["cases"]
    items_by_order = {int(item["candidate_order"]): item for item in items}
    require(len(items_by_order) == len(items), "candidate order collision")
    orders = eligible_orders(items, selected_orders)
    require(len(orders) == 344, f"unexpected independent function candidate count: {len(orders)}")

    old_progress = Path(source["a4_qualification_progress"])
    require(sha256_file(old_progress / "progress-manifest.json") == source["a4_progress_manifest_sha256"], "A4 progress identity changed")
    old_evaluations = load_cached(old_progress, items_by_order)

    paths = config["paths"]
    progress = Path(paths["progress_directory"])
    output = Path(paths["output_directory"])
    require(not output.exists(), "refusing to overwrite dev-exec output")
    identity = {
        "version": PROGRESS_VERSION,
        "config_sha256": sha256_file(args.config),
        "candidate_manifest_sha256": source["candidate_manifest_sha256"],
        "a4_selected_manifest_sha256": source["a4_selected_manifest_sha256"],
        "eligible_function_candidates": len(orders),
        "target_count": config["selection"]["target_count"],
    }
    progress_manifest = progress / "progress-manifest.json"
    if progress_manifest.exists():
        require(json.loads(progress_manifest.read_text(encoding="utf-8")) == identity, "dev progress identity changed")
    else:
        require(not progress.exists() or not any(progress.iterdir()), "dev progress exists without identity")
        progress.mkdir(parents=True, exist_ok=True)
        (progress / "evaluations").mkdir()
        write_json_atomic(progress_manifest, identity)
    (progress / "evaluations").mkdir(exist_ok=True)

    new_evaluations = load_cached(progress, items_by_order)
    require(set(new_evaluations).issubset(set(orders)), "dev progress contains ineligible order")
    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["local_path"], local_files_only=True, trust_remote_code=False, use_fast=True
    )
    require(sha256_file(Path(config["model"]["local_path"]) / "config.json") == config["model"]["config_sha256"], "model config changed")
    qualification = config["qualification"]
    max_tokens = int(qualification["max_input_tokens"])
    allowed_path = str(qualification["allowed_path"])
    bwrap = resolve_bwrap(args.bwrap)

    all_evaluations = {order: old_evaluations[order] for order in orders if order in old_evaluations}
    all_evaluations.update(new_evaluations)
    token_counts: dict[int, int] = {}

    def current_qualified() -> list[int]:
        result: list[int] = []
        for order in orders:
            if order not in all_evaluations:
                continue
            ok, tokens = qualified_with_tokens(all_evaluations[order], candidate_dir, tokenizer, max_tokens, allowed_path)
            if tokens is not None:
                token_counts[order] = tokens
            if ok:
                result.append(order)
        return result

    target = int(config["selection"]["target_count"])
    batch_size = int(qualification["batch_size"])
    print(json.dumps({"event": "dev_qualification_start", "reused": len(all_evaluations), "qualified": len(current_qualified()), "target": target}, sort_keys=True), flush=True)
    with ProcessPoolExecutor(max_workers=int(qualification["workers"])) as executor:
        while len(current_qualified()) < target:
            pending = [items_by_order[order] for order in orders if order not in all_evaluations][:batch_size]
            if not pending:
                break
            futures = [executor.submit(evaluate_candidate, (str(candidate_dir), item, str(bwrap))) for item in pending]
            for future in as_completed(futures):
                value = future.result()
                order = int(value["decision"]["candidate_order"])
                require(order in orders, "evaluation returned ineligible order")
                write_json_atomic(progress / "evaluations" / f"{order:04d}.json", value)
                all_evaluations[order] = value
            print(json.dumps({"event": "dev_qualification_batch", "evaluated": len(all_evaluations), "qualified": len(current_qualified()), "target": target}, sort_keys=True), flush=True)

    qualified_orders = current_qualified()
    minimum = int(config["selection"]["minimum_count"])
    require(len(qualified_orders) >= minimum, f"dev qualification below minimum: {len(qualified_orders)} < {minimum}")
    selected = qualified_orders[:target]
    require(not {items_by_order[order]["case_id"] for order in selected} & selected_case_ids, "A4 selected case reused")
    require(len({items_by_order[order]["problem_id"] for order in selected}) == len(selected), "dev family collision")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="data-v2-dev-exec-building-", dir=output.parent))
    try:
        (temporary / "cases").mkdir()
        manifest_cases: list[dict[str, Any]] = []
        result_rows: list[dict[str, Any]] = []
        reuse_counts: Counter[str] = Counter()
        for order in selected:
            evaluation = all_evaluations[order]
            item = evaluation["selected_item"]
            shutil.copytree(candidate_dir / "cases" / item["case_id"], temporary / "cases" / item["case_id"])
            write_json(temporary / "cases" / item["case_id"] / "test-partition.json", evaluation["partitions"])
            origin = "a4_qualification_reused" if order in old_evaluations else "data_v2_qualification_new"
            reuse_counts[origin] += 1
            bound = dict(item)
            bound["qualification_origin"] = origin
            bound["prompt_tokens"] = token_counts[order]
            bound["case_result_sha256"] = sha256_bytes(json.dumps(evaluation["case_result"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            manifest_cases.append(bound)
            result_rows.append(evaluation["case_result"])
        write_jsonl = lambda path, rows: path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
        write_jsonl(temporary / "qualification-results.jsonl", result_rows)
        manifest = {
            "version": VERSION,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", "local"),
            "config_sha256": sha256_file(args.config),
            "candidate_manifest_sha256": source["candidate_manifest_sha256"],
            "a4_selected_manifest_sha256": source["a4_selected_manifest_sha256"],
            "a4_progress_manifest_sha256": source["a4_progress_manifest_sha256"],
            "source_train_sha256": source["formal_train_sha256"],
            "model": {"model_id": config["model"]["model_id"], "revision": config["model"]["revision"], "config_sha256": config["model"]["config_sha256"]},
            "selected_count": len(selected),
            "minimum_count": minimum,
            "task_level_counts": {"function": len(selected)},
            "qualification_origin_counts": dict(sorted(reuse_counts.items())),
            "a4_selected_overlap": 0,
            "problem_family_unique": True,
            "selection_uses_model_output_or_score": False,
            "evaluation_content_read": False,
            "evaluation_gold_consumed": False,
            "cases": manifest_cases,
        }
        write_json(temporary / "dev-exec-manifest.json", manifest)
        write_json(temporary / "qualification-summary.json", {
            "version": VERSION,
            "eligible_function_candidates": len(orders),
            "evaluated_candidates": len(all_evaluations),
            "qualified_candidates": len(qualified_orders),
            "selected_count": len(selected),
            "target_reached": len(selected) == target,
            "minimum_reached": len(selected) >= minimum,
            "a4_selected_overlap": 0,
        })
        artifacts = [temporary / name for name in ("dev-exec-manifest.json", "qualification-results.jsonl", "qualification-summary.json")]
        artifacts.extend(sorted((temporary / "cases").glob("*/*")))
        (temporary / "sha256sums.txt").write_text("".join(f"{sha256_file(item)[7:]}  {item.relative_to(temporary)}\n" for item in artifacts), encoding="utf-8")
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"output": str(output), "selected": len(selected), "qualified": len(qualified_orders), "manifest_sha256": sha256_file(output / "dev-exec-manifest.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
