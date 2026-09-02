"""Build the reproducible A1 300/50 pilot from the two verified sources."""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def diff_text(old: str, new: str, filename: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=f"a/{filename}", tofile=f"b/{filename}", lineterm="\n"))


def diff_stats(old: str, new: str, filename: str) -> tuple[int, list[int]]:
    additions = deletions = 0
    old_line = 0
    changed_old_lines: list[int] = []
    for line in diff_text(old, new, filename).splitlines():
        if line.startswith("@@"):
            match = re.search(r"-(\d+)(?:,(\d+))?", line)
            old_line = int(match.group(1)) if match else old_line
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            changed_old_lines.append(old_line)
            old_line += 1
        elif line.startswith(" "):
            old_line += 1
    return max(additions, deletions), changed_old_lines


def function_spans(code: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for number, line in enumerate(code.splitlines(), 1):
        for char in line:
            if char == "{":
                stack.append(number)
            elif char == "}" and stack:
                start = stack.pop()
                if start > 1:
                    spans.append((start, number))
    return spans


def classify_level(old: str, changed_old_lines: list[int]) -> str:
    containing = [span for span in function_spans(old) if changed_old_lines and all(span[0] <= line <= span[1] for line in changed_old_lines)]
    return "function" if len(containing) == 1 else "file_window"


def iter_records(path: Path, source: str) -> Iterator[dict[str, Any]]:
    if source == "runbugrun":
        for shard in sorted(path.glob("cpp_*.jsonl.gz")):
            split = "validation" if "valid" in shard.name else "train"
            with gzip.open(shard, "rt", encoding="utf-8") as stream:
                for line in stream:
                    record = json.loads(line)
                    record.update({"_source": source, "_shard": shard.name, "_upstream_split": split})
                    yield record
    else:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                record.update({"_source": source, "_shard": "data/c++/data.jsonl", "_upstream_split": "unassigned"})
                yield record


def eligible(record: dict[str, Any]) -> tuple[bool, str | None, dict[str, Any]]:
    source = record["_source"]
    old = record.get("buggy_code" if source == "runbugrun" else "old_contents", "")
    new = record.get("fixed_code" if source == "runbugrun" else "new_contents", "")
    filename = "main.cpp" if source == "runbugrun" else record.get("old_file", "")
    if not old or not new:
        return False, "missing_code", {}
    if not filename or filename.startswith(("/", "../")) or "\\" in filename or "/../" in filename:
        return False, "invalid_path", {}
    changed, changed_old_lines = diff_stats(old, new, filename)
    expected = record.get("change_count") if source == "runbugrun" else None
    if expected is not None and expected != changed:
        return False, "change_count_mismatch", {}
    if not 1 <= changed <= 40:
        return False, "changed_lines_out_of_range", {}
    if len(old.splitlines()) > 256:
        return False, "source_over_256_lines", {}
    if (len(old) + 256) // 4 > 4096:
        return False, "estimated_tokens_over_4096", {}
    family = f"RunBugRun:problem:{record['problem_id']}" if source == "runbugrun" else (record.get("repos", "").split(",")[0].strip() or "unknown")
    if source == "commitpackft" and record.get("license") in {None, "", "unknown"}:
        return False, "unknown_license", {}
    return True, None, {"old": old, "new": new, "filename": filename, "changed": changed, "level": classify_level(old, changed_old_lines), "family": family}


def make_sample(item: dict[str, Any], split: str, ordinal: int) -> dict[str, Any]:
    record, info = item["record"], item["info"]
    source = record["_source"]
    bug_id = str(record.get("id", record.get("commit")))
    problem = str(record.get("problem_id", record.get("repos", "unknown")))
    base = f"codenet-submission:{record['buggy_submission_id']}" if source == "runbugrun" else f"{record['commit']}^"
    fixed = f"codenet-submission:{record['fixed_submission_id']}" if source == "runbugrun" else str(record["commit"])
    level = info["level"]
    old = info["old"]
    sample: dict[str, Any] = {
        "schema_version": "0.2.0", "sample_id": f"{source[:3]}:{split}:{bug_id}:{ordinal:04d}",
        "source_dataset": "RunBugRun" if source == "runbugrun" else "CommitPackFT",
        "source_revision": "0.0.1" if source == "runbugrun" else "HuggingFace snapshot fc56fe33c030c6daa414c2b112c932b8eed085e6",
        "repo_id": f"IBM-Project-CodeNet:{problem}:{record['buggy_submission_id']}" if source == "runbugrun" else record.get("repos", "").split(",")[0].strip(),
        "repo_family": info["family"], "base_commit": base, "fix_commit": fixed, "language": "cpp", "task_level": level,
        "edit_type": ("single_line" if info["changed"] == 1 else "multi_line_local" if info["changed"] <= 20 else "localized_refactor"), "changed_logical_lines": info["changed"],
        "problem_statement": (record.get("subject") or f"Repair the C++ change in {info['filename']}.") if source == "commitpackft" else f"Repair CodeNet problem {problem}.",
        "failure_evidence": (record.get("message") or "CommitPackFT bug-fix commit evidence.") if source == "commitpackft" else "RunBugRun buggy/fixed pair; executable replay is pending A2.",
        "context": {"target_file": info["filename"], "target_symbol": None, "start_line": 1, "end_line": max(1, len(old.splitlines())), "buggy_code": old},
        "file_window_lines": len(old.splitlines()) if level == "file_window" else None, "file_window_context_before": 0 if level == "file_window" else None, "file_window_context_after": 0 if level == "file_window" else None,
        "input_token_count": max(1, (len(old) + 256) // 4), "allowed_paths": [info["filename"]], "gold_patch": diff_text(old, info["new"], info["filename"]),
        "build_command": ["g++", "-std=c++17", "-O2", info["filename"], "-o", "main"], "public_test_command": None, "hidden_test_command": None, "regression_test_command": None,
        "public_test_count": 0, "hidden_test_count": 0, "regression_test_count": 0, "timeout_seconds": 60, "license": record.get("license", "CodeNet source license; audit required"), "split": split,
    }
    sample["provenance_hash"] = digest({"source_shard": record["_shard"], "source_id": bug_id, "sample": sample})
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commitpack-file", type=Path, required=True)
    parser.add_argument("--runbugrun-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train", type=int, default=300); parser.add_argument("--validation", type=int, default=50)
    parser.add_argument("--train-commitpack", type=int, default=120); parser.add_argument("--validation-commitpack", type=int, default=20)
    args = parser.parse_args()
    wanted = {"train": {"commitpackft": args.train_commitpack, "runbugrun": args.train - args.train_commitpack}, "validation": {"commitpackft": args.validation_commitpack, "runbugrun": args.validation - args.validation_commitpack}}
    pools: dict[str, list[dict[str, Any]]] = {"commitpackft": [], "runbugrun": []}; rejects = Counter(); seen = Counter()
    for source, path in (("commitpackft", args.commitpack_file), ("runbugrun", args.runbugrun_dir)):
        for record in iter_records(path, source):
            seen[source] += 1; ok, reason, info = eligible(record)
            if ok: pools[source].append({"record": record, "info": info})
            else: rejects[f"{source}:{reason}"] += 1
    selected: list[dict[str, Any]] = []; used: dict[str, set[str]] = {"train": set(), "validation": set()}
    for split in ("train", "validation"):
        for source in ("commitpackft", "runbugrun"):
            source_target = wanted[split][source]
            level_targets = {"function": round(source_target * 0.85), "file_window": source_target - round(source_target * 0.85)}
            pool = sorted(pools[source], key=lambda item: hashlib.sha256(f"{item['info']['family']}:{item['record'].get('id', item['record'].get('commit'))}".encode()).hexdigest())
            for level, level_target in level_targets.items():
                count = 0
                for item in pool:
                    family = item["info"]["family"]
                    if item["info"]["level"] != level or family in used[split] or (source == "runbugrun" and item["record"]["_upstream_split"] != split): continue
                    selected.append({**item, "_split": split}); used[split].add(family); count += 1
                    if count == level_target: break
                if count != level_target: raise RuntimeError(f"cannot fill {split}/{source}/{level}: requested {level_target}, got {count}")
    samples = [make_sample(item, item["_split"], index) for index, item in enumerate(selected)]
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):
        with (output / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for sample in samples:
                if sample["split"] == split: stream.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "sample-v0.2.schema.json"; validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    errors = [{"sample_id": s["sample_id"], "message": e.message} for s in samples for e in validator.iter_errors(s)]
    report = {"raw_records_seen": dict(seen), "usable_candidates": {k: len(v) for k, v in pools.items()}, "reject_counts": dict(sorted(rejects.items())), "source_counts": {"train": {"CommitPackFT": args.train_commitpack, "RunBugRun": args.train - args.train_commitpack}, "validation": {"CommitPackFT": args.validation_commitpack, "RunBugRun": args.validation - args.validation_commitpack}}, "task_level_counts": {f"{split}:{level}": sum(s["split"] == split and s["task_level"] == level for s in samples) for split in ("train", "validation") for level in ("function", "file_window")}, "executable_status": "not_executable_until_A2_wrapper_and_sandbox", "limitations": ["RunBugRun standalone CodeNet submissions lack Git commits and natural-language problem statements.", "CommitPackFT repository checkout/build/test replay remains an A2 task.", "Public/hidden/regression commands are null in A1 pilot."]}
    (output / "filter-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "dataset-manifest.json").write_text(json.dumps({"schema_version": "0.2.0", "samples": [{"sample_id": s["sample_id"], "source_dataset": s["source_dataset"], "split": s["split"], "provenance_hash": s["provenance_hash"]} for s in samples]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "split-report.json").write_text(json.dumps({"upstream_split_preserved_for_runbugrun": True, "repository_family_isolation": True, "requested": wanted}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "schema-validation-report.json").write_text(json.dumps({"schema": "schemas/sample-v0.2.schema.json", "sample_count": len(samples), "valid_count": len(samples) - len(errors), "invalid_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors: raise RuntimeError(f"schema validation failed: {len(errors)} errors")
    print(json.dumps({"output_dir": str(output), "samples": len(samples), "report": report}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__": main()
