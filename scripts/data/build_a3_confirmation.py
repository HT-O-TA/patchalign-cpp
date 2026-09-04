"""Build the family-isolated, unseen A3.4 confirmation candidate pool."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from typing import Any

from scripts.data.build_a2_holdout import diff_info, load_tests, pilot_problems, stable
from scripts.data.build_a3_formal_holdout import formal_level, sha256_file, write_json


VERSION = "a3-confirmation-candidate-v1"
CONFIG_VERSION = "a3-confirmation-v1"


def prefixed_sha256(path: Path) -> str:
    return "sha256:" + sha256_file(path)


def validate_config(config: dict[str, Any]) -> None:
    if config.get("version") != CONFIG_VERSION or config.get("seed") != 20260830:
        raise RuntimeError("wrong confirmation config identity")
    if config["source"]["dataset"] != "RunBugRun" or config["source"]["revision"] != "0.0.1":
        raise RuntimeError("wrong confirmation source")
    if config["candidate_counts"] != {"function": 218, "file_window": 53}:
        raise RuntimeError("wrong confirmation candidate counts")
    if config["required_counts"] != {"function": 100, "file_window": 25}:
        raise RuntimeError("wrong confirmation denominator")
    expected_qualification = {
        "double_replay_required": True,
        "problem_family_unique": True,
        "max_input_tokens": 4096,
        "allowed_path": "main.cpp",
        "sandbox": "bubblewrap-0.12.0-rootless-no-network",
    }
    if config["qualification"] != expected_qualification:
        raise RuntimeError("confirmation qualification policy changed")


def verify_inputs(config: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    source = config["source"]
    raw = Path(source["raw_directory"])
    if prefixed_sha256(raw / "source-record.json") != source["source_record_sha256"]:
        raise RuntimeError("RunBugRun source record changed")
    exclusions = config["exclusions"]
    pilot = Path(exclusions["pilot_directory"])
    if prefixed_sha256(pilot / "dataset-manifest.json") != exclusions["pilot_manifest_sha256"]:
        raise RuntimeError("pilot manifest changed")
    sft_path = Path(exclusions["formal_sft_manifest"])
    holdout_path = Path(exclusions["formal_holdout_manifest"])
    if prefixed_sha256(sft_path) != exclusions["formal_sft_manifest_sha256"]:
        raise RuntimeError("formal SFT manifest changed")
    if prefixed_sha256(holdout_path) != exclusions["formal_holdout_manifest_sha256"]:
        raise RuntimeError("formal holdout manifest changed")
    sft = json.loads(sft_path.read_text(encoding="utf-8"))
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    pilot_families = {str(value) for value in pilot_problems(pilot)}
    sft_families = {
        item["repo_family"].rsplit(":", 1)[-1]
        for item in sft["samples"]
        if item["source_dataset"] == "RunBugRun"
    }
    holdout_families = {str(item["problem_id"]) for item in holdout["cases"]}
    if sft_families & holdout_families:
        raise RuntimeError("existing SFT/holdout family isolation is invalid")
    return pilot_families, sft_families, holdout_families


def collect_candidates(config: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str], int]:
    raw = Path(config["source"]["raw_directory"])
    pilot, sft, holdout = verify_inputs(config)
    tests = load_tests(raw / "tests_all.jsonl.gz")
    candidates: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    seen: set[str] = set()
    raw_seen = 0
    for shard in sorted(raw.glob("cpp_*.jsonl.gz")):
        upstream_split = "validation" if "valid" in shard.name else "train"
        with gzip.open(shard, "rt", encoding="utf-8") as stream:
            for line in stream:
                raw_seen += 1
                record = json.loads(line)
                problem = str(record["problem_id"])
                if problem in seen:
                    continue
                old, new = record.get("buggy_code", ""), record.get("fixed_code", "")
                changed, changed_lines = diff_info(old, new)
                reason = None
                if problem in pilot:
                    reason = "pilot_family"
                elif problem in sft:
                    reason = "formal_sft_family"
                elif problem in holdout:
                    reason = "formal_holdout_family"
                elif not old or not new:
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
                seen.add(problem)
                candidates.append({
                    "record": record,
                    "old": old,
                    "new": new,
                    "changed": changed,
                    "level": formal_level(old, changed_lines),
                    "tests": tests[problem],
                    "hash": stable([config["seed"], problem, record["id"]]),
                    "upstream_split": upstream_split,
                    "source_shard": shard.name,
                })
    candidates.sort(key=lambda item: item["hash"])
    return candidates, rejected, raw_seen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    output = Path(config["paths"]["candidate_directory"])
    if output.exists():
        raise RuntimeError(f"refusing to overwrite confirmation candidates: {output}")
    candidates, rejected, raw_seen = collect_candidates(config)
    counts = Counter(item["level"] for item in candidates)
    if dict(counts) != config["candidate_counts"]:
        raise RuntimeError(f"confirmation capacity changed: {dict(counts)}")

    output.mkdir(parents=True)
    samples: list[dict[str, Any]] = []
    for order, item in enumerate(candidates):
        record = item["record"]
        problem = str(record["problem_id"])
        case_id = f"rbr-confirm-{item['hash'][:20]}"
        case_dir = output / "cases" / case_id
        case_dir.mkdir(parents=True)
        (case_dir / "buggy.cpp").write_text(item["old"], encoding="utf-8")
        (case_dir / "fixed.cpp").write_text(item["new"], encoding="utf-8")
        (case_dir / "main.cpp").write_text(item["old"], encoding="utf-8")
        ordered_tests = sorted(item["tests"], key=lambda test: stable([test["id"], test["input"], test["output"]]))
        (case_dir / "tests.jsonl").write_text(
            "".join(json.dumps(test, ensure_ascii=False, sort_keys=True) + "\n" for test in ordered_tests),
            encoding="utf-8",
        )
        samples.append({
            "case_id": case_id,
            "source_dataset": "RunBugRun",
            "source_revision": config["source"]["revision"],
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
        })
    manifest = {
        "version": VERSION,
        "config_sha256": prefixed_sha256(args.config),
        "selection": "stable SHA256; one candidate per family unseen by pilot, formal SFT, and formal holdout",
        "required_task_levels": config["required_counts"],
        "candidate_task_levels": dict(counts),
        "family_exclusion_counts": {"pilot": len(verify_inputs(config)[0]), "formal_sft": len(verify_inputs(config)[1]), "formal_holdout": len(verify_inputs(config)[2])},
        "source_record_sha256": config["source"]["source_record_sha256"],
        "exclusion_manifest_sha256": {
            "pilot": config["exclusions"]["pilot_manifest_sha256"],
            "formal_sft": config["exclusions"]["formal_sft_manifest_sha256"],
            "formal_holdout": config["exclusions"]["formal_holdout_manifest_sha256"],
        },
        "cases": samples,
    }
    report = {
        "version": VERSION,
        "raw_records_seen": raw_seen,
        "candidate_count": len(samples),
        "candidate_task_levels": dict(counts),
        "required_task_levels": config["required_counts"],
        "pre_execution_rejected": dict(sorted(rejected.items())),
        "problem_id_unique": len({item["problem_id"] for item in samples}) == len(samples),
        "family_overlap": {"pilot": 0, "formal_sft": 0, "formal_holdout": 0},
    }
    write_json(output / "candidate-manifest.json", manifest)
    write_json(output / "candidate-report.json", report)
    paths = [output / "candidate-manifest.json", output / "candidate-report.json", *sorted((output / "cases").glob("*/*"))]
    (output / "sha256sums.txt").write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(output)}\n" for path in paths),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "counts": dict(counts), "manifest_sha256": prefixed_sha256(output / "candidate-manifest.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
