"""Build the frozen A3.3 formal executable holdout candidate pool."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.data.build_a2_holdout import (
    diff_info,
    load_tests,
    pilot_problems,
    spans,
    stable,
)


VERSION = "a3-formal-candidate-pool-v1"


def formal_level(code: str, changed: list[int]) -> str:
    containing = [
        span
        for span in spans(code)
        if changed and all(span[0] <= line <= span[1] for line in changed)
    ]
    return "function" if containing else "file_window"


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--function-candidates", type=int, default=900)
    parser.add_argument("--file-window-candidates", type=int, default=250)
    parser.add_argument("--required-function", type=int, default=400)
    parser.add_argument("--required-file-window", type=int, default=100)
    args = parser.parse_args()

    output = args.output_dir.resolve()
    if output.exists():
        raise RuntimeError(f"refusing to overwrite output: {output}")
    excluded = pilot_problems(args.pilot_dir)
    tests = load_tests(args.raw_dir / "tests_all.jsonl.gz")
    candidates: list[dict[str, Any]] = []
    seen_problems: set[str] = set()
    rejected: Counter[str] = Counter()
    raw_records_seen = 0

    for shard in sorted(args.raw_dir.glob("cpp_*.jsonl.gz")):
        upstream_split = "validation" if "valid" in shard.name else "train"
        with gzip.open(shard, "rt", encoding="utf-8") as stream:
            for line in stream:
                raw_records_seen += 1
                record = json.loads(line)
                problem = str(record["problem_id"])
                if problem in excluded or problem in seen_problems:
                    continue
                old = record.get("buggy_code", "")
                new = record.get("fixed_code", "")
                changed, changed_lines = diff_info(old, new)
                reason = None
                if not old or not new:
                    reason = "missing_code"
                elif changed < 1 or changed > 40:
                    reason = "changed_lines_out_of_range"
                elif len(old.splitlines()) > 256:
                    reason = "source_over_256_lines"
                elif (len(old) + 256) // 4 > 4096:
                    reason = "estimated_tokens_over_4096"
                elif len(tests.get(problem, [])) < 5:
                    reason = "fewer_than_five_tests"
                if reason:
                    rejected[reason] += 1
                    continue
                seen_problems.add(problem)
                candidates.append(
                    {
                        "record": record,
                        "old": old,
                        "new": new,
                        "changed": changed,
                        "level": formal_level(old, changed_lines),
                        "tests": tests[problem],
                        "hash": stable([problem, record["id"]]),
                        "upstream_split": upstream_split,
                        "source_shard": shard.name,
                    }
                )

    candidates.sort(key=lambda item: item["hash"])
    available = Counter(item["level"] for item in candidates)
    requested = {
        "function": args.function_candidates,
        "file_window": args.file_window_candidates,
    }
    for task_level, count in requested.items():
        if available[task_level] < count:
            raise RuntimeError(
                f"cannot fill {task_level}: requested {count}, "
                f"found {available[task_level]}"
            )

    chosen: list[dict[str, Any]] = []
    for task_level in ("function", "file_window"):
        matches = [item for item in candidates if item["level"] == task_level]
        chosen.extend(matches[: requested[task_level]])
    if Counter(item["level"] for item in chosen) != Counter(requested):
        raise RuntimeError("candidate selection composition mismatch")

    output.mkdir(parents=True)
    samples: list[dict[str, Any]] = []
    for order, item in enumerate(chosen):
        record = item["record"]
        problem = str(record["problem_id"])
        identity = stable([problem, record["id"]])
        case_id = f"rbr-formal-{identity[:20]}"
        case_dir = output / "cases" / case_id
        case_dir.mkdir(parents=True)
        (case_dir / "buggy.cpp").write_text(item["old"], encoding="utf-8")
        (case_dir / "fixed.cpp").write_text(item["new"], encoding="utf-8")
        (case_dir / "main.cpp").write_text(item["old"], encoding="utf-8")
        ordered_tests = sorted(
            item["tests"],
            key=lambda test: stable([test["id"], test["input"], test["output"]]),
        )
        (case_dir / "tests.jsonl").write_text(
            "".join(
                json.dumps(test, ensure_ascii=False, sort_keys=True) + "\n"
                for test in ordered_tests
            ),
            encoding="utf-8",
        )
        samples.append(
            {
                "case_id": case_id,
                "source_dataset": "RunBugRun",
                "source_revision": "0.0.1",
                "source_shard": item["source_shard"],
                "upstream_split": item["upstream_split"],
                "problem_id": problem,
                "bug_id": record["id"],
                "task_level": item["level"],
                "changed_logical_lines": item["changed"],
                "buggy_submission_id": record["buggy_submission_id"],
                "fixed_submission_id": record["fixed_submission_id"],
                "test_count": len(ordered_tests),
                "candidate_order": order,
                "sanitizer_applicable": False,
                "sanitizer_status": "not_applicable",
                "license": "CodeNet source license; audit required",
            }
        )

    manifest = {
        "version": VERSION,
        "selection": "stable SHA256; one candidate per unseen problem_id",
        "excluded_pilot_problem_ids": sorted(excluded),
        "required_task_levels": {
            "function": args.required_function,
            "file_window": args.required_file_window,
        },
        "candidate_task_levels": requested,
        "cases": samples,
    }
    report = {
        "version": VERSION,
        "raw_records_seen": raw_records_seen,
        "eligible_problem_families": len(candidates),
        "available_task_levels": dict(available),
        "candidate_pool_count": len(samples),
        "candidate_task_levels": dict(Counter(x["task_level"] for x in samples)),
        "pre_execution_rejected": dict(sorted(rejected.items())),
        "pilot_problem_exclusion": True,
        "problem_id_unique": len({x["problem_id"] for x in samples}) == len(samples),
    }
    write_json(output / "candidate-manifest.json", manifest)
    write_json(output / "candidate-report.json", report)
    artifact_paths = [
        output / "candidate-manifest.json",
        output / "candidate-report.json",
        *sorted((output / "cases").glob("*/*")),
    ]
    (output / "sha256sums.txt").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output)}\n"
            for path in artifact_paths
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_dir": str(output),
                "counts": dict(Counter(x["task_level"] for x in samples)),
                "manifest_sha256": sha256_file(output / "candidate-manifest.json"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
