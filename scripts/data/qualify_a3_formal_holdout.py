"""Qualify and freeze the 400/100 A3.3 executable holdout."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator
from transformers import AutoTokenizer

from scripts.baseline.run_a3_baseline import build_prompt, render_model_input
from scripts.data.a2_output_matcher import matcher_metadata
from scripts.data.a2_sandbox_runtime import SANDBOX_VERSION, resolve_bwrap
from scripts.data.a2_stability import stable_replay
from scripts.data.qualify_a2_holdout import (
    load_tests,
    partition_ids,
    rejection_reasons,
    repartition_version,
)
from scripts.data.run_a2_cases import execute_version, resolve_case, sanitizer_record


VERSION = "a3-formal-holdout-v1"
PROGRESS_VERSION = "a3-formal-qualification-progress-v1"


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_json_atomic(path: Path, value: object) -> None:
    """Write one checkpoint without exposing a partial JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    write_json(temporary, value)
    temporary.replace(path)


def progress_identity(
    candidate_manifest: dict[str, Any],
    candidate_manifest_sha256: str,
) -> dict[str, Any]:
    return {
        "version": PROGRESS_VERSION,
        "source_candidate_version": candidate_manifest["version"],
        "source_candidate_manifest_sha256": candidate_manifest_sha256,
        "required_task_levels": candidate_manifest["required_task_levels"],
        "sandbox_policy_version": SANDBOX_VERSION,
        "output_matcher": matcher_metadata(),
    }


def load_cached_evaluations(
    progress_dir: Path,
    items_by_order: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    evaluations: dict[int, dict[str, Any]] = {}
    for path in sorted((progress_dir / "evaluations").glob("*.json")):
        evaluation = json.loads(path.read_text(encoding="utf-8"))
        decision = evaluation["decision"]
        order = decision["candidate_order"]
        item = items_by_order.get(order)
        if item is None:
            raise RuntimeError(f"checkpoint has unknown candidate_order: {path}")
        for key in ("case_id", "problem_id", "task_level", "candidate_order"):
            if decision[key] != item[key]:
                raise RuntimeError(f"checkpoint identity mismatch for {path}: {key}")
        if order in evaluations:
            raise RuntimeError(f"duplicate checkpoint for candidate_order={order}")
        evaluations[order] = evaluation
    return evaluations


def qualified_count(
    items: list[dict[str, Any]],
    evaluations: dict[int, dict[str, Any]],
) -> int:
    return sum(
        bool(evaluations[item["candidate_order"]]["decision"]["qualified"])
        for item in items
        if item["candidate_order"] in evaluations
    )


def prompt_token_count(
    candidate_dir: Path,
    evaluation: dict[str, Any],
    tokenizer: Any,
    allowed_path: str,
) -> int:
    """Count the exact raw-completion input used by formal inference."""
    item = evaluation["selected_item"]
    case_dir = candidate_dir / "cases" / item["case_id"]
    tests = {
        str(test["id"]): test
        for test in map(
            json.loads,
            (case_dir / "tests.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }
    public_id = str(evaluation["partitions"]["public"][0])
    prompt = build_prompt(
        item,
        (case_dir / "buggy.cpp").read_text(encoding="utf-8"),
        tests[public_id],
        allowed_path,
    )
    rendered = render_model_input(tokenizer, prompt, "raw_completion")
    return len(tokenizer(rendered, add_special_tokens=True)["input_ids"])


def selectable_count(
    items: list[dict[str, Any]],
    evaluations: dict[int, dict[str, Any]],
    prompt_tokens: dict[int, int],
    max_input_tokens: int,
) -> int:
    return sum(
        bool(evaluations[order]["decision"]["qualified"])
        and prompt_tokens.get(order, max_input_tokens + 1) <= max_input_tokens
        for item in items
        if (order := item["candidate_order"]) in evaluations
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_candidate(payload: tuple[str, dict[str, Any], str]) -> dict[str, Any]:
    candidate_root, item, bwrap_string = payload
    candidate_dir = Path(candidate_root)
    bwrap = Path(bwrap_string)
    case = resolve_case(candidate_dir, item["case_id"], require_partition=False)
    tests, ordered_ids = load_tests(case)
    sanitizer_record(item)
    suites = {"all": ordered_ids}
    versions = {
        version: execute_version(
            case,
            version,
            str(item["problem_id"]),
            bwrap,
            tests,
            suites,
            stop_on_timeout=True,
        )
        for version in ("buggy", "fixed")
    }
    execution_complete = all(
        versions[version]["compile"]["status"] == "pass"
        and len(versions[version].get("suites", {}).get("all", []))
        == len(ordered_ids)
        for version in versions
    )
    if execution_complete:
        partitions, counts = partition_ids(
            ordered_ids, versions["buggy"], versions["fixed"]
        )
    else:
        partitions = {"regression": [], "public": [], "hidden": []}
        counts = {
            "tests": len(ordered_ids),
            "fixed_failures": len(ordered_ids),
            "target_failures": 0,
            "regression_passes": 0,
        }
    reasons = rejection_reasons(
        versions["buggy"],
        versions["fixed"],
        counts,
        execution_complete=execution_complete,
    )
    stability_replayed = False
    if not reasons:
        stability_replayed = True
        replay = {
            version: execute_version(
                case,
                version,
                str(item["problem_id"]),
                bwrap,
                tests,
                suites,
                stop_on_timeout=True,
            )
            for version in ("buggy", "fixed")
        }
        if not stable_replay(versions, replay):
            reasons.append("nondeterministic_replay")

    decision = {
        "case_id": item["case_id"],
        "problem_id": item["problem_id"],
        "task_level": item["task_level"],
        "candidate_order": item["candidate_order"],
        "selected": False,
        "qualified": not reasons,
        "stability_replayed": stability_replayed,
        "reasons": reasons,
        **counts,
    }
    if reasons:
        return {"decision": decision}

    selected_item = {
        key: value for key, value in item.items() if key != "candidate_order"
    }
    selected_item["source_candidate_order"] = item["candidate_order"]
    selected_item["test_partition"] = partitions
    case_result = {
        "schema_version": "0.2.0-draft",
        "case_id": item["case_id"],
        "problem_id": item["problem_id"],
        "task_level": item["task_level"],
        "sandbox": {
            "backend": "bubblewrap",
            "policy_version": SANDBOX_VERSION,
        },
        "output_matcher": matcher_metadata(),
        "sanitizer": sanitizer_record(item),
        "versions": {
            version: repartition_version(versions[version], partitions)
            for version in ("buggy", "fixed")
        },
        "acceptance": {
            "buggy_target_failure_observed": True,
            "fixed_all_tests_matched": True,
            "partition_contract_satisfied": True,
        },
    }
    return {
        "decision": decision,
        "partitions": partitions,
        "selected_item": selected_item,
        "case_result": case_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--progress-dir", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--max-input-tokens", type=int, default=4096)
    parser.add_argument("--allowed-path", default="main.cpp")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("workers must be positive")
    if args.batch_size < 1:
        raise SystemExit("batch-size must be positive")
    if args.max_input_tokens < 1:
        raise SystemExit("max-input-tokens must be positive")
    bwrap = resolve_bwrap(args.bwrap)
    if args.holdout_dir.exists():
        raise SystemExit(f"refusing to overwrite holdout: {args.holdout_dir}")

    candidate_manifest_path = args.candidate_dir / "candidate-manifest.json"
    candidate_manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    if candidate_manifest["version"] != "a3-formal-candidate-pool-v1":
        raise RuntimeError("unexpected formal candidate version")
    required = candidate_manifest["required_task_levels"]
    items = candidate_manifest["cases"]
    items_by_order = {item["candidate_order"]: item for item in items}
    if len(items_by_order) != len(items):
        raise RuntimeError("candidate_order values must be unique")
    levels = ["function", "file_window"]
    if set(required) != set(levels):
        raise RuntimeError(f"unexpected required task levels: {sorted(required)}")
    unknown_levels = sorted({item["task_level"] for item in items} - set(levels))
    if unknown_levels:
        raise RuntimeError(f"candidate manifest has unknown task levels: {unknown_levels}")

    identity = progress_identity(candidate_manifest, sha256_file(candidate_manifest_path))
    progress_manifest_path = args.progress_dir / "progress-manifest.json"
    if progress_manifest_path.exists():
        existing_identity = json.loads(
            progress_manifest_path.read_text(encoding="utf-8")
        )
        if existing_identity != identity:
            raise RuntimeError(
                "qualification progress does not match the candidate manifest or policy"
            )
    else:
        unexpected_progress = (
            [
                path
                for path in args.progress_dir.iterdir()
                if path.name != ".progress-manifest.json.tmp"
            ]
            if args.progress_dir.exists()
            else []
        )
        if unexpected_progress:
            raise RuntimeError(
                f"progress directory is non-empty without manifest: {args.progress_dir}"
            )
        args.progress_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(progress_manifest_path, identity)

    evaluations = load_cached_evaluations(args.progress_dir, items_by_order)
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    prompt_tokens = {
        order: prompt_token_count(
            args.candidate_dir, evaluation, tokenizer, args.allowed_path
        )
        for order, evaluation in evaluations.items()
        if evaluation["decision"]["qualified"]
    }
    items_by_level = {
        level: [item for item in items if item["task_level"] == level]
        for level in levels
    }
    print(
        json.dumps(
            {
                "event": "qualification_resume",
                "cached": len(evaluations),
                "total_candidates": len(items),
                "qualified_by_level": {
                    level: qualified_count(items_by_level[level], evaluations)
                    for level in levels
                },
                "selectable_by_level": {
                    level: selectable_count(
                        items_by_level[level],
                        evaluations,
                        prompt_tokens,
                        args.max_input_tokens,
                    )
                    for level in levels
                },
            },
            sort_keys=True,
        ),
        flush=True,
    )

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for level in levels:
            level_items = items_by_level[level]
            while (
                selectable_count(
                    level_items,
                    evaluations,
                    prompt_tokens,
                    args.max_input_tokens,
                )
                < required[level]
            ):
                pending = [
                    item
                    for item in level_items
                    if item["candidate_order"] not in evaluations
                ][: args.batch_size]
                if not pending:
                    break
                payloads = [
                    (str(args.candidate_dir), item, str(bwrap))
                    for item in pending
                ]
                futures = [
                    executor.submit(evaluate_candidate, payload)
                    for payload in payloads
                ]
                completed = 0
                for future in as_completed(futures):
                    evaluation = future.result()
                    decision = evaluation["decision"]
                    order = decision["candidate_order"]
                    checkpoint_path = (
                        args.progress_dir
                        / "evaluations"
                        / f"{order:04d}.json"
                    )
                    write_json_atomic(checkpoint_path, evaluation)
                    evaluations[order] = evaluation
                    if decision["qualified"]:
                        prompt_tokens[order] = prompt_token_count(
                            args.candidate_dir,
                            evaluation,
                            tokenizer,
                            args.allowed_path,
                        )
                    completed += 1
                print(
                    json.dumps(
                        {
                            "event": "qualification_batch_complete",
                            "task_level": level,
                            "batch_size": completed,
                            "evaluated": len(evaluations),
                            "qualified": qualified_count(level_items, evaluations),
                            "selectable": selectable_count(
                                level_items,
                                evaluations,
                                prompt_tokens,
                                args.max_input_tokens,
                            ),
                            "required": required[level],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

    selected_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    decisions: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for order in sorted(evaluations):
        evaluation = evaluations[order]
        decision = dict(evaluation["decision"])
        task_level = decision["task_level"]
        if decision["qualified"]:
            order = decision["candidate_order"]
            decision["prompt_tokens"] = prompt_tokens[order]
            if prompt_tokens[order] > args.max_input_tokens:
                decision["qualified"] = False
                decision["reasons"] = [
                    *decision["reasons"],
                    "prompt_tokens_over_limit",
                ]
        if decision["qualified"] and selected_counts[task_level] < required[task_level]:
            decision["selected"] = True
            selected.append(evaluation)
            selected_counts[task_level] += 1
        elif decision["reasons"]:
            rejection_counts.update(decision["reasons"])
        decisions.append(decision)

    missing = {
        level: required[level] - selected_counts[level]
        for level in required
        if selected_counts[level] < required[level]
    }
    if missing:
        raise RuntimeError(f"candidate pool could not fill formal holdout: {missing}")

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "a2-execution-v0.2.schema.json"
    )
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    for evaluation in selected:
        validator.validate(evaluation["case_result"])

    args.holdout_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix="a3-formal-holdout-building-",
            dir=args.holdout_dir.parent,
        )
    )
    try:
        (temporary / "cases").mkdir()
        selected_manifest: list[dict[str, Any]] = []
        selected_results: list[dict[str, Any]] = []
        for evaluation in selected:
            item = evaluation["selected_item"]
            source = args.candidate_dir / "cases" / item["case_id"]
            destination = temporary / "cases" / item["case_id"]
            shutil.copytree(source, destination)
            write_json(destination / "test-partition.json", evaluation["partitions"])
            selected_manifest.append(item)
            selected_results.append(evaluation["case_result"])

        manifest = {
            "version": VERSION,
            "source_candidate_version": candidate_manifest["version"],
            "source_candidate_manifest_sha256": sha256_file(
                args.candidate_dir / "candidate-manifest.json"
            ),
            "task_level_counts": dict(selected_counts),
            "partition_rule": (
                "F=buggy-fail/fixed-pass; public=stable first ceil(20%) "
                "of F; hidden=remaining F; regression=buggy-pass/fixed-pass"
            ),
            "output_matcher": matcher_metadata(),
            "prompt_token_policy": {
                "model_config_sha256": sha256_file(args.model_path / "config.json"),
                "input_mode": "raw_completion",
                "allowed_path": args.allowed_path,
                "max_input_tokens": args.max_input_tokens,
            },
            "cases": selected_manifest,
        }
        report = {
            "version": VERSION,
            "selected_count": len(selected_manifest),
            "selected_task_levels": dict(selected_counts),
            "evaluated_candidates": len(decisions),
            "unevaluated_candidates": len(items) - len(decisions),
            "qualified_candidates": sum(d["qualified"] for d in decisions),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "prompt_token_policy": manifest["prompt_token_policy"],
            "selected_prompt_token_stats": {
                "count": len(selected),
                "min": min(d["prompt_tokens"] for d in decisions if d["selected"]),
                "max": max(d["prompt_tokens"] for d in decisions if d["selected"]),
                "total": sum(d["prompt_tokens"] for d in decisions if d["selected"]),
            },
            "workers": args.workers,
            "batch_size": args.batch_size,
            "progress_version": PROGRESS_VERSION,
            "decisions": decisions,
        }
        write_json(temporary / "a2-manifest.json", manifest)
        write_json(temporary / "qualification-report.json", report)
        (temporary / "qualification-results.jsonl").write_text(
            "".join(
                json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
                for result in selected_results
            ),
            encoding="utf-8",
        )
        artifact_paths = [
            temporary / "a2-manifest.json",
            temporary / "qualification-report.json",
            temporary / "qualification-results.jsonl",
            *sorted((temporary / "cases").glob("*/*")),
        ]
        (temporary / "sha256sums.txt").write_text(
            "".join(
                f"{sha256_file(path)}  {path.relative_to(temporary)}\n"
                for path in artifact_paths
            ),
            encoding="utf-8",
        )
        temporary.rename(args.holdout_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(
        json.dumps(
            {
                "holdout_dir": str(args.holdout_dir),
                "selected": len(selected),
                "counts": dict(selected_counts),
                "manifest_sha256": sha256_file(
                    args.holdout_dir / "a2-manifest.json"
                ),
                "qualification_results_sha256": sha256_file(
                    args.holdout_dir / "qualification-results.jsonl"
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
