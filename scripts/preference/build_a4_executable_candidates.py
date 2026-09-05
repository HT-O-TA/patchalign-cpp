"""Build train-only RunBugRun candidates for exploratory A4 preference data."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.data.build_a2_holdout import load_tests
from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "a4-executable-preference-data-v1"
CANDIDATE_VERSION = "a4-executable-candidate-pool-v1"
MODE = "owner_authorized_exploratory"
EXPECTED_TRAIN_SHA = "sha256:c1cd80868632b845fa80a249ef8083ad2f5cf709e54dad63bcfe492a3ee3b400"
EXPECTED_MANIFEST_SHA = "sha256:50b0dd1b49a7f14297e2e70871be910673b725ece8de4795938548d256384c02"
EXPECTED_SOURCE_RECORD_SHA = "sha256:047305c1b01cbe4e00e700b5ad053cfcceed0df0fea6605c47aeaddb353940fa"
EXPECTED_TESTS_SHA = "sha256:2fab824c5dd5244e1471d38655faea668fc6cd6a669cb4ce124d1fee7ce70d96"


def stable(parts: list[object]) -> str:
    payload = "\0".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong A4 data version")
    require(config.get("mode") == MODE, "A4 must remain exploratory")
    require(config.get("seed") == 20260830, "wrong A4 seed")
    source = config["source"]
    require(source["formal_train"] == "/mingli01/data/patchalign-cpp/a3/formal-sft-v1/train.jsonl", "wrong A4 train source")
    require(source["formal_train_sha256"] == EXPECTED_TRAIN_SHA, "A4 train hash changed")
    require(source["formal_manifest_sha256"] == EXPECTED_MANIFEST_SHA, "A4 formal manifest changed")
    require(source["runbugrun_source_record_sha256"] == EXPECTED_SOURCE_RECORD_SHA, "RunBugRun source record changed")
    require(source["runbugrun_tests_sha256"] == EXPECTED_TESTS_SHA, "RunBugRun tests changed")
    selection = config["selection"]
    require(selection == {
        "source_dataset": "RunBugRun",
        "split": "train",
        "language": "cpp",
        "candidate_counts": {"function": 600, "file_window": 26},
        "required_counts": {"function": 256, "file_window": 8},
        "maximum_samples_per_problem_family": 1,
        "order": "sha256(seed, sample_id) among problems with at least 5 tests; file_window selected first, then function",
    }, "A4 selection policy changed")
    qualification = config["qualification"]
    require(qualification["double_replay_required"] is True, "A4 double replay disabled")
    require(qualification["network"] == "unshared", "A4 network isolation changed")
    require(qualification["sanitizer"] == "only_if_explicitly_applicable", "A4 sanitizer policy changed")
    forbidden = " ".join(config["leakage_policy"]["forbidden"])
    for name in ("validation", "internal holdout", "confirmation", "Defects4C"):
        require(name in forbidden, f"missing forbidden A4 source: {name}")


def select_train_rows(
    config: dict[str, Any], testable_families: set[str] | None = None
) -> list[dict[str, Any]]:
    rows = read_jsonl(Path(config["source"]["formal_train"]))
    all_eligible = [
        row for row in rows
        if row["source_dataset"] == "RunBugRun"
        and row["split"] == "train"
        and row["language"] == "cpp"
    ]
    require(len(all_eligible) == 2956, "A3.3 train-only RunBugRun count changed")
    eligible = [
        row for row in all_eligible
        if testable_families is None or row["repo_family"] in testable_families
    ]
    by_level = {
        level: sorted(
            (row for row in eligible if row["task_level"] == level),
            key=lambda row: stable([config["seed"], row["sample_id"]]),
        )
        for level in ("file_window", "function")
    }
    selected: list[dict[str, Any]] = []
    used_families: set[str] = set()
    for level in ("file_window", "function"):
        target = config["selection"]["candidate_counts"][level]
        for row in by_level[level]:
            if row["repo_family"] in used_families:
                continue
            selected.append(row)
            used_families.add(row["repo_family"])
            if sum(item["task_level"] == level for item in selected) == target:
                break
        require(sum(item["task_level"] == level for item in selected) == target, f"cannot fill A4 {level} candidates")
    require(len(used_families) == len(selected), "A4 problem family overlap")
    return selected


def load_testable_families(
    raw_dir: Path, tests: dict[str, list[dict[str, Any]]]
) -> set[str]:
    """Return train problem families with the frozen minimum test coverage."""
    families: set[str] = set()
    for path in sorted(raw_dir.glob("cpp_train*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                problem = str(json.loads(line)["problem_id"])
                if len(tests.get(problem, [])) >= 5:
                    families.add(f"RunBugRun:problem:{problem}")
    return families


def raw_records(raw_dir: Path, selected: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
    wanted = {int(row["sample_id"].split(":")[2]) for row in selected}
    found: dict[int, dict[str, Any]] = {}
    shards: dict[int, str] = {}
    for path in sorted(raw_dir.glob("cpp_train*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                identifier = int(record["id"])
                if identifier in wanted:
                    require(identifier not in found, f"duplicate RunBugRun id: {identifier}")
                    found[identifier] = record
                    shards[identifier] = path.name
    require(set(found) == wanted, "selected A4 train records missing from RunBugRun train shards")
    return found, shards


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    source = config["source"]
    for key, path_key in (("formal_train_sha256", "formal_train"), ("formal_manifest_sha256", "formal_manifest")):
        require(sha256_file(Path(source[path_key])) == source[key], f"A4 source hash mismatch: {path_key}")
    raw_dir = Path(source["runbugrun_directory"])
    require(sha256_file(raw_dir / "source-record.json") == source["runbugrun_source_record_sha256"], "RunBugRun source-record mismatch")
    require(sha256_file(raw_dir / "tests_all.jsonl.gz") == source["runbugrun_tests_sha256"], "RunBugRun tests mismatch")
    output = Path(config["paths"]["candidate_directory"])
    require(not output.exists(), "refusing to overwrite A4 candidate directory")

    tests = load_tests(raw_dir / "tests_all.jsonl.gz")
    testable_families = load_testable_families(raw_dir, tests)
    selected = select_train_rows(config, testable_families)
    raw_by_id, shards = raw_records(raw_dir, selected)
    output.mkdir(parents=True)
    cases: list[dict[str, Any]] = []
    for order, train in enumerate(selected):
        raw_id = int(train["sample_id"].split(":")[2])
        raw = raw_by_id[raw_id]
        problem = str(raw["problem_id"])
        require(train["repo_family"] == f"RunBugRun:problem:{problem}", "A4 problem family mismatch")
        require(train["context"]["buggy_code"] == raw["buggy_code"], "A4 buggy source mismatch")
        require(str(train["base_commit"]).endswith(str(raw["buggy_submission_id"])), "A4 buggy submission mismatch")
        require(str(train["fix_commit"]).endswith(str(raw["fixed_submission_id"])), "A4 fixed submission mismatch")
        require(problem in tests and len(tests[problem]) >= 5, "A4 test source missing")
        identity = stable([config["seed"], train["sample_id"]])
        case_id = f"rbr-a4-{identity[:20]}"
        case_dir = output / "cases" / case_id
        case_dir.mkdir(parents=True)
        (case_dir / "buggy.cpp").write_text(raw["buggy_code"], encoding="utf-8")
        (case_dir / "fixed.cpp").write_text(raw["fixed_code"], encoding="utf-8")
        (case_dir / "main.cpp").write_text(raw["buggy_code"], encoding="utf-8")
        ordered_tests = sorted(tests[problem], key=lambda test: stable([test["id"], test["input"], test["output"]]))
        (case_dir / "tests.jsonl").write_text("".join(json.dumps(test, ensure_ascii=False, sort_keys=True) + "\n" for test in ordered_tests), encoding="utf-8")
        cases.append({
            "case_id": case_id,
            "source_dataset": "RunBugRun",
            "source_revision": "0.0.1",
            "source_shard": shards[raw_id],
            "upstream_split": "train",
            "source_train_sample_id": train["sample_id"],
            "source_train_provenance_hash": train["provenance_hash"],
            "problem_id": problem,
            "bug_id": raw_id,
            "task_level": train["task_level"],
            "changed_logical_lines": train["changed_logical_lines"],
            "buggy_submission_id": raw["buggy_submission_id"],
            "fixed_submission_id": raw["fixed_submission_id"],
            "gold_patch_sha256": sha256_file_bytes(train["gold_patch"].encode("utf-8")),
            "test_count": len(ordered_tests),
            "candidate_order": order,
            "sanitizer_applicable": False,
            "sanitizer_status": "not_applicable",
            "license": train["license"],
        })

    manifest = {
        "version": CANDIDATE_VERSION,
        "mode": MODE,
        "source_train_sha256": source["formal_train_sha256"],
        "source_manifest_sha256": source["formal_manifest_sha256"],
        "source_runbugrun_record_sha256": source["runbugrun_source_record_sha256"],
        "source_tests_sha256": source["runbugrun_tests_sha256"],
        "selection": config["selection"]["order"],
        "required_task_levels": config["selection"]["required_counts"],
        "candidate_task_levels": config["selection"]["candidate_counts"],
        "leakage_audit": {
            "source_split": "train",
            "validation_records": 0,
            "internal_records": 0,
            "confirmation_records": 0,
            "external_records": 0,
            "problem_family_unique": True,
        },
        "cases": cases,
    }
    testable_rows = [row for row in read_jsonl(Path(source["formal_train"])) if row.get("repo_family") in testable_families]
    report = {
        "version": CANDIDATE_VERSION,
        "eligible_train_runbugrun": 2956,
        "testable_train_runbugrun": len(testable_rows),
        "testable_task_levels": dict(Counter(row["task_level"] for row in testable_rows)),
        "minimum_test_count": 5,
        "candidate_count": len(cases),
        "candidate_task_levels": dict(Counter(case["task_level"] for case in cases)),
        "problem_family_unique": len({case["problem_id"] for case in cases}) == len(cases),
    }
    write_json(output / "candidate-manifest.json", manifest)
    write_json(output / "candidate-report.json", report)
    artifacts = [output / "candidate-manifest.json", output / "candidate-report.json", *sorted((output / "cases").glob("*/*"))]
    (output / "sha256sums.txt").write_text("".join(f"{sha256_file(path)[7:]}  {path.relative_to(output)}\n" for path in artifacts), encoding="utf-8")
    print(json.dumps({"output": str(output), "counts": report["candidate_task_levels"], "manifest_sha256": sha256_file(output / "candidate-manifest.json")}, sort_keys=True))


def sha256_file_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    main()
