"""Build the A1 300/50 pilot from the verified RunBugRun C++ shards.

RunBugRun records are standalone CodeNet submissions, not Git repositories.
The generated records therefore use an explicit ``codenet-submission:`` base
identifier and are marked non-executable for A1; A2 must wrap and replay a
selected subset before any hidden-test result is reported.
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def records(raw_dir: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(raw_dir.glob("cpp_*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                record["_shard"] = path.name
                yield record


def patch_for(old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile="a/main.cpp",
        tofile="b/main.cpp",
        lineterm="\n",
    )
    return "".join(lines)


def changed_lines(old: str, new: str) -> int:
    additions = 0
    deletions = 0
    for line in patch_for(old, new).splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return max(additions, deletions)


def make_sample(record: dict[str, Any], split: str, ordinal: int, level: str) -> dict[str, Any]:
    old = record["buggy_code"]
    new = record["fixed_code"]
    changed = changed_lines(old, new)
    patch = patch_for(old, new)
    problem_id = str(record["problem_id"])
    bug_id = str(record["id"])
    sample: dict[str, Any] = {
        "schema_version": "0.2.0",
        "sample_id": f"rbr:{split}:{bug_id}:{ordinal:04d}",
        "source_dataset": "RunBugRun",
        "source_revision": "0.0.1",
        "repo_id": f"IBM-Project-CodeNet:{problem_id}:{record['buggy_submission_id']}",
        "repo_family": f"RunBugRun:problem:{problem_id}",
        "base_commit": f"codenet-submission:{record['buggy_submission_id']}",
        "fix_commit": f"codenet-submission:{record['fixed_submission_id']}",
        "language": "cpp",
        "task_level": level,
        "edit_type": "single_line" if changed == 1 else "multi_line_local",
        "changed_logical_lines": changed,
        "problem_statement": (
            f"Repair the buggy C++ submission for CodeNet problem {problem_id}. "
            "The source release does not include the original natural-language problem statement."
        ),
        "failure_evidence": "RunBugRun labels this buggy/fixed pair; executable replay is pending A2.",
        "context": {
            "target_file": "main.cpp",
            "target_symbol": "main",
            "start_line": 1,
            "end_line": max(1, len(old.splitlines())),
            "buggy_code": old,
        },
        "file_window_lines": len(old.splitlines()) if level == "file_window" else None,
        "file_window_context_before": 0 if level == "file_window" else None,
        "file_window_context_after": 0 if level == "file_window" else None,
        "input_token_count": max(1, (len(old) + 256) // 4),
        "allowed_paths": ["main.cpp"],
        "gold_patch": patch,
        "build_command": ["g++", "-std=c++17", "-O2", "main.cpp", "-o", "main"],
        "public_test_command": None,
        "hidden_test_command": None,
        "regression_test_command": None,
        "public_test_count": 0,
        "hidden_test_count": 0,
        "regression_test_count": 0,
        "timeout_seconds": 60,
        "license": "CodeNet source license; audit required per record",
        "split": split,
    }
    sample["provenance_hash"] = digest(
        {"source_shard": record["_shard"], "source_id": record["id"], "sample": sample}
    )
    return sample


def select(raw_dir: Path, train_count: int, validation_count: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_problems: set[str] = set()
    for record in records(raw_dir):
        old = record.get("buggy_code", "")
        new = record.get("fixed_code", "")
        lines = old.splitlines()
        changed = changed_lines(old, new)
        reason = None
        if not old or not new:
            reason = "missing_code"
        elif record.get("change_count") != changed:
            reason = "change_count_mismatch"
        elif changed < 1 or changed > 40:
            reason = "changed_lines_out_of_range"
        elif len(lines) > 256:
            reason = "source_over_256_lines"
        elif max(1, (len(old) + 256) // 4) > 4096:
            reason = "estimated_tokens_over_4096"
        elif record["problem_id"] in seen_problems:
            reason = "problem_id_reserved_for_split_isolation"
        if reason is None:
            level = "file_window" if len(lines) > 96 or changed > 1 else "function"
            candidates.append({"record": record, "level": level})
        else:
            candidates.append({"rejected": reason})

    usable = [item for item in candidates if "record" in item]
    # Stable ordering plus problem-level reservation prevents train/validation overlap.
    usable.sort(key=lambda item: hashlib.sha256(f"{item['record']['problem_id']}:{item['record']['id']}".encode()).hexdigest())
    chosen: list[dict[str, Any]] = []
    reserved: set[str] = set()
    for item in usable:
        problem = item["record"]["problem_id"]
        if problem in reserved:
            continue
        chosen.append(item)
        reserved.add(problem)
        if len(chosen) == train_count + validation_count:
            break
    if len(chosen) < train_count + validation_count:
        raise RuntimeError(f"only {len(chosen)} isolated candidates available")

    train = chosen[:train_count]
    validation = chosen[train_count:]
    function_train = round(train_count * 0.85)
    function_validation = round(validation_count * 0.85)
    samples: list[dict[str, Any]] = []
    for index, item in enumerate(train):
        level = "function" if index < function_train else "file_window"
        samples.append(make_sample(item["record"], "train", index, level))
    for index, item in enumerate(validation):
        level = "function" if index < function_validation else "file_window"
        samples.append(make_sample(item["record"], "validation", index, level))
    report = {
        "source": "RunBugRun v0.0.1",
        "selection_policy": "stable SHA256 order; one problem_id per split assignment",
        "raw_records_seen": len(candidates),
        "usable_before_split_isolation": len(usable),
        "train_count": train_count,
        "validation_count": validation_count,
        "function_count": function_train + function_validation,
        "file_window_count": train_count + validation_count - function_train - function_validation,
        "executable_status": "not_executable_until_A2_wrapper_and_sandbox",
        "known_limitations": [
            "RunBugRun records are standalone CodeNet submissions, not Git commits.",
            "Selected release payload has no natural-language problem statement.",
            "Public/hidden/regression commands are null for this A1 pilot.",
            "License strings require source-level audit before publication.",
        ],
    }
    return samples, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train", type=int, default=300)
    parser.add_argument("--validation", type=int, default=50)
    args = parser.parse_args()
    samples, report = select(args.raw_dir, args.train, args.validation)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):
        path = output / f"{split}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for sample in samples:
                if sample["split"] == split:
                    stream.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
    (output / "filter-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "0.2.0",
        "source_dataset": "RunBugRun",
        "source_revision": "0.0.1",
        "samples": [{"sample_id": s["sample_id"], "split": s["split"], "provenance_hash": s["provenance_hash"]} for s in samples],
    }
    (output / "dataset-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "split-report.json").write_text(json.dumps({"train": args.train, "validation": args.validation, "problem_id_isolation": True}, indent=2) + "\n", encoding="utf-8")
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "sample-v0.2.schema.json"
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    validation_errors = []
    for sample in samples:
        for error in validator.iter_errors(sample):
            validation_errors.append({"sample_id": sample["sample_id"], "message": error.message})
    validation_report = {
        "schema": "schemas/sample-v0.2.schema.json",
        "sample_count": len(samples),
        "valid_count": len(samples) - len(validation_errors),
        "invalid_count": len(validation_errors),
        "errors": validation_errors,
    }
    (output / "schema-validation-report.json").write_text(json.dumps(validation_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if validation_errors:
        raise RuntimeError(f"schema validation failed for {len(validation_errors)} fields")
    print(json.dumps({"output_dir": str(output), **report}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
