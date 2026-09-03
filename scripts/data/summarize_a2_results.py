"""Validate and deterministically summarize an A2 execution JSONL artifact."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def summarize(records: list[dict[str, Any]], source_sha256: str) -> dict[str, Any]:
    case_ids = [str(record["case_id"]) for record in records]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("execution result contains duplicate case_id values")
    task_levels = Counter(str(record["task_level"]) for record in records)
    acceptance_keys = (
        "buggy_target_failure_observed",
        "fixed_all_tests_matched",
        "partition_contract_satisfied",
    )
    summary: dict[str, Any] = {
        "source_sha256": source_sha256,
        "case_count": len(records),
        "task_level_counts": dict(sorted(task_levels.items())),
        "schema_versions": dict(sorted(Counter(record["schema_version"] for record in records).items())),
        "matcher_versions": dict(sorted(Counter(record["output_matcher"]["version"] for record in records).items())),
        "acceptance_true_counts": {
            key: sum(bool(record["acceptance"][key]) for record in records)
            for key in acceptance_keys
        },
        "versions": {},
    }
    for version in ("buggy", "fixed"):
        compile_statuses = Counter()
        suite_counts: dict[str, Counter[str]] = {
            suite: Counter() for suite in ("regression", "public", "hidden")
        }
        timeouts = truncations = 0
        for record in records:
            version_result = record["versions"][version]
            compile_statuses[version_result["compile"]["status"]] += 1
            timeouts += int(version_result["compile"]["timed_out"])
            truncations += int(version_result["compile"]["stdout_truncated"])
            truncations += int(version_result["compile"]["stderr_truncated"])
            for suite, outcomes in version_result.get("suites", {}).items():
                suite_counts[suite]["total"] += len(outcomes)
                suite_counts[suite]["matched"] += sum(item["matched"] for item in outcomes)
                timeouts += sum(item["timed_out"] for item in outcomes)
                truncations += sum(
                    item["stdout_truncated"] or item["stderr_truncated"]
                    for item in outcomes
                )
        summary["versions"][version] = {
            "compile_statuses": dict(sorted(compile_statuses.items())),
            "suites": {
                suite: dict(counts) for suite, counts in suite_counts.items()
            },
            "timeout_count": timeouts,
            "truncation_count": truncations,
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "schemas" / "a2-execution-v0.2.schema.json",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite summary: {args.output}")
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)
    records = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in records:
        validator.validate(record)
    result = summarize(records, sha256(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
