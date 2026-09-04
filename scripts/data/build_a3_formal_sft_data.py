"""Build the frozen A3.3 5,000/500 formal SFT dataset."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator
from transformers import AutoTokenizer

from scripts.data.build_a1_pilot import (
    digest,
    diff_stats,
    diff_text,
    eligible,
    function_spans,
    iter_records,
    make_sample,
)
from scripts.training.train_a3_sft_pilot import encode_example


VERSION = "a3-formal-sft-data-v1"
MAX_PER_FAMILY = 2
TARGETS = {
    "train": {
        ("commitpackft", "function"): 1320,
        ("commitpackft", "file_window"): 723,
        ("runbugrun", "function"): 2930,
        ("runbugrun", "file_window"): 27,
    },
    "validation": {
        ("commitpackft", "function"): 129,
        ("commitpackft", "file_window"): 71,
        ("runbugrun", "function"): 296,
        ("runbugrun", "file_window"): 4,
    },
}
EDIT_TARGETS = {
    "train": {
        "single_line": 1750,
        "multi_line_local": 2500,
        "add_helper": 500,
        "localized_refactor": 250,
    },
    "validation": {
        "single_line": 175,
        "multi_line_local": 250,
        "add_helper": 50,
        "localized_refactor": 25,
    },
}
FUNCTION_PATTERN = re.compile(
    r"(?m)^[^#\n;{}]*?\b([A-Za-z_]\w*)\s*"
    r"\([^;{}]*\)\s*(?:const\s*)?\{"
)
CONTROL_NAMES = {"if", "for", "while", "switch", "catch"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def function_names(code: str) -> set[str]:
    return {match.group(1) for match in FUNCTION_PATTERN.finditer(code)} - CONTROL_NAMES


def classify_edit(old: str, new: str, changed: int) -> str:
    added_functions = function_names(new) - function_names(old)
    for name in added_functions:
        if len(re.findall(rf"\b{re.escape(name)}\s*\(", new)) >= 2:
            return "add_helper"
    if changed == 1:
        return "single_line"
    if changed <= 20:
        return "multi_line_local"
    return "localized_refactor"


def formal_level(old: str, filename: str, new: str) -> str:
    _, changed_lines = diff_stats(old, new, filename)
    containing = [
        span
        for span in function_spans(old)
        if changed_lines and all(span[0] <= line <= span[1] for line in changed_lines)
    ]
    return "function" if containing else "file_window"


def source_key(record: dict[str, Any]) -> str:
    value = record.get("id") or record.get("commit")
    if value is None:
        raise RuntimeError("source record has neither id nor commit")
    return str(value)


def sample_seed_key(sample: dict[str, Any]) -> tuple[str, str]:
    source = "runbugrun" if sample["source_dataset"] == "RunBugRun" else "commitpackft"
    parts = sample["sample_id"].split(":")
    if len(parts) < 4:
        raise RuntimeError(f"cannot recover source id: {sample['sample_id']}")
    return source, parts[2]


def payload_key_from_sample(sample: dict[str, Any]) -> str:
    payload = {
        "source": sample["source_dataset"],
        "old": sample["context"]["buggy_code"],
        "patch": sample["gold_patch"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def payload_key_from_item(item: dict[str, Any]) -> str:
    source = (
        "RunBugRun"
        if item["record"]["_source"] == "runbugrun"
        else "CommitPackFT"
    )
    payload = {
        "source": source,
        "old": item["info"]["old"],
        "patch": diff_text(
            item["info"]["old"],
            item["info"]["new"],
            item["info"]["filename"],
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def counts_by_cell(samples: list[dict[str, Any]], split: str) -> Counter[tuple[str, str]]:
    result: Counter[tuple[str, str]] = Counter()
    for sample in samples:
        if sample["split"] != split:
            continue
        source = (
            "runbugrun"
            if sample["source_dataset"] == "RunBugRun"
            else "commitpackft"
        )
        result[(source, sample["task_level"])] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commitpack-file", type=Path, required=True)
    parser.add_argument("--runbugrun-dir", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_dir.resolve()
    if output.exists():
        raise RuntimeError(f"refusing to overwrite output: {output}")
    holdout_manifest = json.loads(
        (args.holdout_dir / "a2-manifest.json").read_text(encoding="utf-8")
    )
    if holdout_manifest["version"] != "a3-formal-holdout-v1":
        raise RuntimeError("unexpected formal holdout version")
    holdout_problems = {str(item["problem_id"]) for item in holdout_manifest["cases"]}
    if len(holdout_problems) != 500:
        raise RuntimeError("formal holdout must contain 500 unique problem families")

    seeds: list[dict[str, Any]] = []
    for split in ("train", "validation"):
        path = args.pilot_dir / f"{split}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            sample = json.loads(line)
            if sample["split"] != split:
                raise RuntimeError(f"pilot split mismatch: {sample['sample_id']}")
            seeds.append(sample)
    if len(seeds) != 350:
        raise RuntimeError("formal data must embed the frozen 300/50 pilot")

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    selected = list(seeds)
    used_source_keys = {sample_seed_key(sample) for sample in seeds}
    used_payloads = {payload_key_from_sample(sample) for sample in seeds}
    family_split: dict[str, str] = {}
    family_counts: Counter[tuple[str, str]] = Counter()
    for sample in seeds:
        family = sample["repo_family"]
        split = sample["split"]
        if family in family_split and family_split[family] != split:
            raise RuntimeError(f"pilot family overlap: {family}")
        family_split[family] = split
        family_counts[(split, family)] += 1
        if family_counts[(split, family)] > MAX_PER_FAMILY:
            raise RuntimeError(f"pilot exceeds family cap: {family}")

    pools: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    rejects: Counter[str] = Counter()
    raw_seen: Counter[str] = Counter()
    paths = {
        "commitpackft": args.commitpack_file,
        "runbugrun": args.runbugrun_dir,
    }
    for source, path in paths.items():
        for record in iter_records(path, source):
            raw_seen[source] += 1
            ok, reason, info = eligible(record)
            if not ok:
                rejects[f"{source}:{reason}"] += 1
                continue
            if (source, source_key(record)) in used_source_keys:
                continue
            if source == "runbugrun" and str(record["problem_id"]) in holdout_problems:
                rejects["runbugrun:formal_holdout_family"] += 1
                continue
            level = formal_level(info["old"], info["filename"], info["new"])
            info = {
                **info,
                "level": level,
                "edit_type": classify_edit(
                    info["old"], info["new"], info["changed"]
                ),
            }
            split = record["_upstream_split"] if source == "runbugrun" else "unassigned"
            item = {"record": record, "info": info}
            item["payload_key"] = payload_key_from_item(item)
            item["sort_key"] = hashlib.sha256(
                (
                    f"{source}:{info['family']}:{source_key(record)}:"
                    f"{item['payload_key']}"
                ).encode()
            ).hexdigest()
            pools[(source, split, level)].append(item)
    for pool in pools.values():
        pool.sort(key=lambda item: item["sort_key"])

    cell_counts = {
        split: counts_by_cell(selected, split)
        for split in ("train", "validation")
    }
    ordinal = len(selected)
    token_rejections: Counter[str] = Counter()

    def fill(split: str, source: str, level: str, target: int) -> None:
        nonlocal ordinal
        have = cell_counts[split][(source, level)]
        if have > target:
            raise RuntimeError(
                f"pilot exceeds target {split}/{source}/{level}: {have}>{target}"
            )
        upstream = split if source == "runbugrun" else "unassigned"
        for item in pools[(source, upstream, level)]:
            if have == target:
                break
            record = item["record"]
            info = item["info"]
            family = info["family"]
            if item["payload_key"] in used_payloads:
                continue
            if family in family_split and family_split[family] != split:
                continue
            if family_counts[(split, family)] >= MAX_PER_FAMILY:
                continue
            proposed = make_sample(
                {**item, "info": info},
                split,
                ordinal,
            )
            proposed["sample_id"] = (
                f"{source[:3]}:formal-{split}:"
                f"{source_key(record)}:{ordinal:05d}"
            )
            proposed["task_level"] = level
            proposed["edit_type"] = info["edit_type"]
            proposed["provenance_hash"] = digest(
                {
                    "source_shard": record["_shard"],
                    "source_id": source_key(record),
                    "sample": {
                        key: value
                        for key, value in proposed.items()
                        if key != "provenance_hash"
                    },
                }
            )
            try:
                encode_example(tokenizer, proposed, 4096)
            except RuntimeError:
                token_rejections[f"{split}:{source}:{level}"] += 1
                continue
            selected.append(proposed)
            used_payloads.add(item["payload_key"])
            used_source_keys.add((source, source_key(record)))
            family_split.setdefault(family, split)
            family_counts[(split, family)] += 1
            have += 1
            ordinal += 1
        if have != target:
            raise RuntimeError(
                f"cannot fill {split}/{source}/{level}: requested {target}, got {have}"
            )
        cell_counts[split][(source, level)] = have

    for split in ("validation", "train"):
        for source in ("commitpackft", "runbugrun"):
            for level in ("function", "file_window"):
                fill(split, source, level, TARGETS[split][(source, level)])

    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "sample-v0.2.schema.json"
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    errors = [
        {"sample_id": sample["sample_id"], "message": error.message}
        for sample in selected
        for error in validator.iter_errors(sample)
    ]
    if errors:
        raise RuntimeError(f"schema validation failed: {len(errors)} errors")

    split_samples = {
        split: sorted(
            (sample for sample in selected if sample["split"] == split),
            key=lambda sample: sample["sample_id"],
        )
        for split in ("train", "validation")
    }
    actual_counts = {split: len(records) for split, records in split_samples.items()}
    if actual_counts != {"train": 5000, "validation": 500}:
        raise RuntimeError(f"formal denominator mismatch: {actual_counts}")

    families = {
        split: {sample["repo_family"] for sample in records}
        for split, records in split_samples.items()
    }
    overlap = families["train"] & families["validation"]
    rbr_problem_sets = {
        split: {
            sample["repo_family"].rsplit(":", 1)[-1]
            for sample in records
            if sample["source_dataset"] == "RunBugRun"
        }
        for split, records in split_samples.items()
    }
    if overlap:
        raise RuntimeError(f"train/validation family overlap: {sorted(overlap)[:10]}")
    if (rbr_problem_sets["train"] | rbr_problem_sets["validation"]) & holdout_problems:
        raise RuntimeError("formal holdout family leaked into SFT data")

    output.mkdir(parents=True)
    for split, records in split_samples.items():
        (output / f"{split}.jsonl").write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    source_counts = {
        split: dict(Counter(x["source_dataset"] for x in records))
        for split, records in split_samples.items()
    }
    task_counts = {
        split: dict(Counter(x["task_level"] for x in records))
        for split, records in split_samples.items()
    }
    edit_counts = {
        split: dict(Counter(x["edit_type"] for x in records))
        for split, records in split_samples.items()
    }
    report = {
        "version": VERSION,
        "raw_records_seen": dict(raw_seen),
        "reject_counts": dict(sorted(rejects.items())),
        "token_rejections": dict(sorted(token_rejections.items())),
        "counts": actual_counts,
        "source_counts": source_counts,
        "task_level_counts": task_counts,
        "edit_type_targets": EDIT_TARGETS,
        "edit_type_actual": edit_counts,
        "edit_type_deviation": {
            split: {
                edit: edit_counts[split].get(edit, 0) - target
                for edit, target in EDIT_TARGETS[split].items()
            }
            for split in EDIT_TARGETS
        },
        "pilot_embedded": {"train": 300, "validation": 50},
        "max_samples_per_repository_family": MAX_PER_FAMILY,
        "train_validation_family_overlap_count": 0,
        "formal_holdout_problem_overlap_count": 0,
        "limitations": [
            "Modification-type percentages are ADR targets; source scarcity is reported, not synthesized.",
            "RunBugRun may contribute at most two distinct pairs per problem family within one split.",
            "CommitPackFT executable checkout/test replay is not available for SFT-only records.",
        ],
    }
    manifest_samples = [
        {
            "sample_id": sample["sample_id"],
            "source_dataset": sample["source_dataset"],
            "split": sample["split"],
            "repo_family": sample["repo_family"],
            "provenance_hash": sample["provenance_hash"],
        }
        for split in ("train", "validation")
        for sample in split_samples[split]
    ]
    manifest = {
        "version": VERSION,
        "schema_version": "0.2.0",
        "formal_holdout_manifest_sha256": sha256_file(
            args.holdout_dir / "a2-manifest.json"
        ),
        "selection_policy": (
            "stable SHA256; pilot embedded; global family split; "
            "exact source and task-level cells; maximum two samples per family"
        ),
        "samples": manifest_samples,
    }
    write_json(output / "dataset-manifest.json", manifest)
    write_json(output / "filter-report.json", report)
    write_json(
        output / "split-report.json",
        {
            "version": VERSION,
            "repository_family_isolation": True,
            "repository_family_overlap_count": 0,
            "formal_holdout_problem_isolation": True,
            "formal_holdout_problem_overlap_count": 0,
            "unique_repository_families": {
                split: len(value) for split, value in families.items()
            },
            "maximum_samples_per_repository_family": MAX_PER_FAMILY,
        },
    )
    write_json(
        output / "schema-validation-report.json",
        {
            "schema": "schemas/sample-v0.2.schema.json",
            "sample_count": sum(actual_counts.values()),
            "valid_count": sum(actual_counts.values()),
            "invalid_count": 0,
            "errors": [],
        },
    )
    artifact_names = (
        "dataset-manifest.json",
        "filter-report.json",
        "schema-validation-report.json",
        "split-report.json",
        "train.jsonl",
        "validation.jsonl",
    )
    (output / "sha256sums.txt").write_text(
        "".join(
            f"{sha256_file(output / name)}  {name}\n"
            for name in artifact_names
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_dir": str(output),
                "counts": actual_counts,
                "source_counts": source_counts,
                "task_counts": task_counts,
                "edit_counts": edit_counts,
                "manifest_sha256": sha256_file(output / "dataset-manifest.json"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
