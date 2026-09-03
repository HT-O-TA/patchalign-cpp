"""Replay A2 candidates and freeze only cases satisfying the test contract."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

try:
    from .a2_output_matcher import matcher_metadata
    from .a2_sandbox_runtime import SANDBOX_VERSION, resolve_bwrap
    from .run_a2_cases import execute_version, resolve_case, sanitizer_record
except ImportError:
    from a2_output_matcher import matcher_metadata
    from a2_sandbox_runtime import SANDBOX_VERSION, resolve_bwrap
    from run_a2_cases import execute_version, resolve_case, sanitizer_record


def load_tests(case: Path) -> tuple[dict[str, dict[str, Any]], list[Any]]:
    tests: dict[str, dict[str, Any]] = {}
    ordered_ids = []
    for line in (case / "tests.jsonl").read_text(encoding="utf-8").splitlines():
        test = json.loads(line)
        key = str(test["id"])
        if key in tests:
            raise RuntimeError(f"duplicate test id {key} in {case}")
        tests[key] = test
        ordered_ids.append(test["id"])
    return tests, ordered_ids


def partition_ids(
    ordered_ids: list[Any], buggy: dict[str, Any], fixed: dict[str, Any]
) -> tuple[dict[str, list[Any]], dict[str, int]]:
    buggy_outcomes = {
        str(item["test_id"]): item for item in buggy.get("suites", {}).get("all", [])
    }
    fixed_outcomes = {
        str(item["test_id"]): item for item in fixed.get("suites", {}).get("all", [])
    }
    fixed_failures = [
        test_id for test_id in ordered_ids if not fixed_outcomes[str(test_id)]["matched"]
    ]
    target = [
        test_id
        for test_id in ordered_ids
        if fixed_outcomes[str(test_id)]["matched"]
        and not buggy_outcomes[str(test_id)]["matched"]
    ]
    regression = [
        test_id
        for test_id in ordered_ids
        if fixed_outcomes[str(test_id)]["matched"]
        and buggy_outcomes[str(test_id)]["matched"]
    ]
    if len(target) >= 2:
        public_count = min(len(target) - 1, max(1, (len(target) + 4) // 5))
    else:
        public_count = 0
    partitions = {
        "regression": regression,
        "public": target[:public_count],
        "hidden": target[public_count:],
    }
    counts = {
        "tests": len(ordered_ids),
        "fixed_failures": len(fixed_failures),
        "target_failures": len(target),
        "regression_passes": len(regression),
    }
    return partitions, counts


def repartition_version(
    version_result: dict[str, Any], partitions: dict[str, list[Any]]
) -> dict[str, Any]:
    outcomes = {
        str(item["test_id"]): item
        for item in version_result.get("suites", {}).get("all", [])
    }
    result = {"compile": version_result["compile"], "suites": {}, "summary": {}}
    if "compile_error_tail" in version_result:
        result["compile_error_tail"] = version_result["compile_error_tail"]
    for suite, ids in partitions.items():
        selected = [outcomes[str(test_id)] for test_id in ids]
        result["suites"][suite] = selected
        result["summary"][suite] = {
            "total": len(selected),
            "matched": sum(item["matched"] for item in selected),
            "all_matched": bool(selected) and all(item["matched"] for item in selected),
        }
    return result


def rejection_reasons(
    buggy: dict[str, Any], fixed: dict[str, Any], counts: dict[str, int]
) -> list[str]:
    reasons = []
    if buggy["compile"]["status"] != "pass":
        reasons.append("buggy_compile_failed")
    if fixed["compile"]["status"] != "pass":
        reasons.append("fixed_compile_failed")
    if counts["fixed_failures"]:
        reasons.append("fixed_test_failed")
    if counts["target_failures"] < 2:
        reasons.append("fewer_than_two_target_failures")
    if counts["regression_passes"] < 3:
        reasons.append("fewer_than_three_regression_passes")
    return reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, default=shutil.which("bwrap"))
    args = parser.parse_args()
    if args.bwrap is None:
        raise SystemExit("sandbox_unavailable: bwrap is required; no untrusted code was executed")
    bwrap = resolve_bwrap(args.bwrap)
    if args.holdout_dir.exists():
        raise SystemExit(f"refusing to overwrite holdout: {args.holdout_dir}")
    candidate_manifest = json.loads(
        (args.candidate_dir / "candidate-manifest.json").read_text(encoding="utf-8")
    )
    required = candidate_manifest["required_task_levels"]
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "a2-execution-v0.2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)
    selected_counts = Counter()
    rejection_counts = Counter()
    decisions = []
    selected_manifest = []
    selected_results = []
    args.holdout_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix="a2-holdout-v2-building-", dir=args.holdout_dir.parent)
    )
    try:
        (temporary / "cases").mkdir()
        for item in candidate_manifest["cases"]:
            task_level = item["task_level"]
            if selected_counts[task_level] >= required[task_level]:
                continue
            case = resolve_case(args.candidate_dir, item["case_id"], require_partition=False)
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
                )
                for version in ("buggy", "fixed")
            }
            if all(versions[v]["compile"]["status"] == "pass" for v in versions):
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
            reasons = rejection_reasons(versions["buggy"], versions["fixed"], counts)
            decision = {
                "case_id": item["case_id"],
                "problem_id": item["problem_id"],
                "task_level": task_level,
                "candidate_order": item["candidate_order"],
                "selected": not reasons,
                "reasons": reasons,
                **counts,
            }
            decisions.append(decision)
            if reasons:
                rejection_counts.update(reasons)
                continue
            destination = temporary / "cases" / item["case_id"]
            shutil.copytree(case, destination)
            (destination / "test-partition.json").write_text(
                json.dumps(partitions, indent=2) + "\n", encoding="utf-8"
            )
            selected_item = {
                key: value for key, value in item.items() if key != "candidate_order"
            }
            selected_item["source_candidate_order"] = item["candidate_order"]
            selected_item["test_partition"] = partitions
            selected_manifest.append(selected_item)
            case_result = {
                "schema_version": "0.2.0-draft",
                "case_id": item["case_id"],
                "problem_id": item["problem_id"],
                "task_level": task_level,
                "sandbox": {"backend": "bubblewrap", "policy_version": SANDBOX_VERSION},
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
            validator.validate(case_result)
            selected_results.append(case_result)
            selected_counts[task_level] += 1
        missing = {
            level: required[level] - selected_counts[level]
            for level in required
            if selected_counts[level] < required[level]
        }
        if missing:
            raise RuntimeError(f"candidate pool could not fill holdout: {missing}")
        manifest = {
            "version": "a2-holdout-v2",
            "source_candidate_version": candidate_manifest["version"],
            "task_level_counts": dict(selected_counts),
            "partition_rule": "F=buggy-fail/fixed-pass; public=stable first ceil(20%) of F; hidden=remaining F; regression=buggy-pass/fixed-pass",
            "output_matcher": matcher_metadata(),
            "cases": selected_manifest,
        }
        report = {
            "selected_count": len(selected_manifest),
            "selected_task_levels": dict(selected_counts),
            "evaluated_candidates": len(decisions),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "decisions": decisions,
        }
        (temporary / "a2-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (temporary / "qualification-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (temporary / "qualification-results.jsonl").write_text(
            "\n".join(
                json.dumps(result, ensure_ascii=False, sort_keys=True)
                for result in selected_results
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.rename(args.holdout_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({
        "holdout_dir": str(args.holdout_dir),
        "selected": len(selected_manifest),
        "evaluated": len(decisions),
        "rejections": dict(sorted(rejection_counts.items())),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
