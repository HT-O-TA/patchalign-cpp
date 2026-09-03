"""Build a deterministic A2 candidate pool without executing source programs."""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def stable(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def patch_text(old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a/main.cpp",
            tofile="b/main.cpp",
            lineterm="\n",
        )
    )


def diff_info(old: str, new: str) -> tuple[int, list[int]]:
    additions = deletions = 0
    old_line = 0
    changed: list[int] = []
    for line in patch_text(old, new).splitlines():
        if line.startswith("@@"):
            match = re.search(r"-(\d+)", line)
            old_line = int(match.group(1)) if match else old_line
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
            changed.append(max(old_line, 1))
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            changed.append(old_line)
            old_line += 1
        elif line.startswith(" "):
            old_line += 1
    return max(additions, deletions), changed


def spans(code: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    stack: list[int] = []
    for number, line in enumerate(code.splitlines(), 1):
        for char in line:
            if char == "{":
                stack.append(number)
            elif char == "}" and stack:
                start = stack.pop()
                if start > 1:
                    result.append((start, number))
    return result


def level(code: str, changed: list[int]) -> str:
    containing = [
        span
        for span in spans(code)
        if changed and all(span[0] <= line <= span[1] for line in changed)
    ]
    return "function" if len(containing) == 1 else "file_window"


def pilot_problems(pilot_dir: Path) -> set[str]:
    result: set[str] = set()
    for path in (pilot_dir / "train.jsonl", pilot_dir / "validation.jsonl"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            sample = json.loads(line)
            match = re.search(r"RunBugRun:problem:([^:]+)", sample.get("repo_family", ""))
            if match:
                result.add(match.group(1))
    return result


def load_tests(path: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            result.setdefault(record["problem_id"], []).append(record)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--function-candidates", type=int, default=75)
    parser.add_argument("--file-window-candidates", type=int, default=30)
    parser.add_argument("--required-function", type=int, default=50)
    parser.add_argument("--required-file-window", type=int, default=20)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    excluded = pilot_problems(args.pilot_dir)
    tests = load_tests(args.raw_dir / "tests_all.jsonl.gz")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    rejected: dict[str, int] = {}
    raw_records_seen = 0
    for shard in sorted(args.raw_dir.glob("cpp_*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as stream:
            for line in stream:
                raw_records_seen += 1
                record = json.loads(line)
                problem = record["problem_id"]
                if problem in excluded or problem in seen:
                    continue
                old, new = record.get("buggy_code", ""), record.get("fixed_code", "")
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
                    rejected[reason] = rejected.get(reason, 0) + 1
                    continue
                seen.add(problem)
                candidates.append(
                    {
                        "record": record,
                        "old": old,
                        "new": new,
                        "changed": changed,
                        "level": level(old, changed_lines),
                        "tests": tests[problem],
                        "hash": stable([problem, record["id"]]),
                    }
                )
    candidates.sort(key=lambda item: item["hash"])
    chosen: list[dict[str, Any]] = []
    requested = (
        ("function", args.function_candidates),
        ("file_window", args.file_window_candidates),
    )
    for wanted_level, count in requested:
        matches = [item for item in candidates if item["level"] == wanted_level]
        if len(matches) < count:
            raise RuntimeError(
                f"cannot fill {wanted_level}: requested {count}, found {len(matches)}"
            )
        chosen.extend(matches[:count])
    samples: list[dict[str, Any]] = []
    for index, item in enumerate(chosen):
        record = item["record"]
        problem = record["problem_id"]
        case_id = f"rbr-a2-{index:04d}-{stable([problem, record['id']])[:16]}"
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
                "problem_id": problem,
                "bug_id": record["id"],
                "task_level": item["level"],
                "changed_logical_lines": item["changed"],
                "buggy_submission_id": record["buggy_submission_id"],
                "fixed_submission_id": record["fixed_submission_id"],
                "test_count": len(ordered_tests),
                "candidate_order": index,
                "sanitizer_applicable": False,
                "sanitizer_status": "not_applicable",
                "license": "CodeNet source license; audit required",
            }
        )
    manifest = {
        "version": "a2-candidate-pool-v2",
        "excluded_pilot_problem_ids": sorted(excluded),
        "required_task_levels": {
            "function": args.required_function,
            "file_window": args.required_file_window,
        },
        "candidate_task_levels": {
            "function": args.function_candidates,
            "file_window": args.file_window_candidates,
        },
        "cases": samples,
    }
    report = {
        "raw_records_seen": raw_records_seen,
        "eligible_before_execution": len(candidates),
        "candidate_pool_count": len(samples),
        "candidate_task_levels": {
            key: sum(sample["task_level"] == key for sample in samples)
            for key in ("function", "file_window")
        },
        "pre_execution_rejected": rejected,
        "problem_id_exclusion": True,
        "selection": "stable SHA256; one structural candidate per unseen problem_id; execution qualification deferred to A2b",
    }
    (output / "candidate-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "candidate-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output_dir": str(output), "candidates": len(samples)}, sort_keys=True))


if __name__ == "__main__":
    main()
