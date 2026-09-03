"""Qualify and freeze the 400/100 A3.3 executable holdout."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

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


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
    parser.add_argument("--bwrap", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("workers must be positive")
    bwrap = resolve_bwrap(args.bwrap)
    if args.holdout_dir.exists():
        raise SystemExit(f"refusing to overwrite holdout: {args.holdout_dir}")

    candidate_manifest = json.loads(
        (args.candidate_dir / "candidate-manifest.json").read_text(encoding="utf-8")
    )
    if candidate_manifest["version"] != "a3-formal-candidate-pool-v1":
        raise RuntimeError("unexpected formal candidate version")
    required = candidate_manifest["required_task_levels"]
    items = candidate_manifest["cases"]
    payloads = [
        (str(args.candidate_dir), item, str(bwrap))
        for item in items
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        evaluations = list(
            executor.map(evaluate_candidate, payloads, chunksize=1)
        )

    selected_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    decisions: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for evaluation in evaluations:
        decision = evaluation["decision"]
        task_level = decision["task_level"]
        if decision["qualified"] and selected_counts[task_level] < required[task_level]:
            decision["selected"] = True
            evaluation["selected_item"]["test_partition"] = evaluation["partitions"]
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
            "cases": selected_manifest,
        }
        report = {
            "version": VERSION,
            "selected_count": len(selected_manifest),
            "selected_task_levels": dict(selected_counts),
            "evaluated_candidates": len(decisions),
            "qualified_candidates": sum(d["qualified"] for d in decisions),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "workers": args.workers,
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
