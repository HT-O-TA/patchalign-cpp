"""Audit real Data-v2 supply without creating training data or reading evaluation gold."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from transformers import AutoTokenizer

from scripts.data.build_a1_pilot import eligible, iter_records, make_sample
from scripts.data.build_a3_formal_sft_data import (
    classify_edit,
    formal_level,
    payload_key_from_item,
    payload_key_from_sample,
    source_key,
)
from scripts.training.train_a3_sft_pilot import encode_example


VERSION = "data-v2-supply-audit-v1"
EXPECTED_EXTERNAL_PROJECTS = {
    "danmar___cppcheck",
    "llvm___llvm-project",
    "skypjack___entt",
    "uncrustify___uncrustify",
    "wez___atomicparsley",
    "zeromq___libzmq",
}
FEATURE_KEYS = (
    "new_family",
    "code_lines_ge_100",
    "prompt_tokens_ge_1024",
    "complex_edit",
    "structural_edit",
    "file_window",
    "commitpackft",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def stable_hash(*values: object) -> str:
    payload = json.dumps(
        values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_file(spec: dict[str, Any], label: str) -> Path:
    path = Path(spec["path"])
    require(path.is_file(), f"missing {label}: {path}")
    actual = sha256_file(path)
    require(actual == spec["sha256"], f"{label} hash changed: {actual}")
    return path


def normalized_family(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def matches_external_alias(family: str, aliases: list[str]) -> bool:
    normalized = normalized_family(family)
    return any(normalized_family(alias) in normalized for alias in aliases)


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected Data-v2 audit version")
    require(config.get("seed") == 20260830, "unexpected Data-v2 seed")
    isolation = config["isolation"]
    require(
        isolation["maximum_samples_per_family_across_v1_plus_increment"] == 2,
        "family cap changed",
    )
    require(
        isolation["commitpack_validation_percent_for_new_families"] == 10,
        "CommitPack split rule changed",
    )
    require(
        isolation["exclude_formal_holdout_problem_families"] is True,
        "holdout exclusion disabled",
    )
    require(
        isolation["exclude_confirmation_problem_families"] is True,
        "confirmation exclusion disabled",
    )
    require(
        isolation["confirmation_or_external_gold_consumed"] is False,
        "evaluation gold must stay unread",
    )
    require(
        isolation["evaluation_fields_consumed"]
        == {
            "formal_holdout": ["problem_id"],
            "confirmation": ["problem_id"],
            "external": ["project"],
        },
        "evaluation metadata boundary changed",
    )
    require(isolation["prefilter_candidates_per_family"] == 8, "prefilter cap changed")
    policy = config["candidate_policy"]
    require(policy["max_sequence_tokens"] == 4096, "sequence limit changed")
    require(policy["long_code_min_lines"] == 100, "long-code boundary changed")
    require(policy["long_prompt_min_tokens"] == 1024, "long-prompt boundary changed")
    require(
        set(policy["complex_edit_types"])
        == {"multi_line_local", "add_helper", "localized_refactor"},
        "complex edit definition changed",
    )
    require(
        set(policy["structural_edit_types"])
        == {"add_helper", "localized_refactor"},
        "structural edit definition changed",
    )
    for split, total in (("train", 2000), ("validation", 200)):
        require(
            config["provisional_increment"][split]["total"] == total,
            f"{split} total changed",
        )
    model = config["model"]
    require(model["model_id"] == "Qwen/Qwen2.5-Coder-7B", "model id changed")
    require(
        model["revision"] == "0396a76181e127dfc13e5c5ec48a8cee09938b02",
        "model revision changed",
    )


def load_frozen_state(config: dict[str, Any]) -> dict[str, Any]:
    frozen = config["frozen_inputs"]
    paths = {name: verify_file(spec, name) for name, spec in frozen.items()}
    train = read_jsonl(paths["formal_train"])
    validation = read_jsonl(paths["formal_validation"])
    require(len(train) == frozen["formal_train"]["count"], "formal train count changed")
    require(
        len(validation) == frozen["formal_validation"]["count"],
        "formal validation count changed",
    )
    manifest = read_json(paths["formal_manifest"])
    require(
        manifest.get("version") == "a3-formal-sft-data-v1",
        "formal manifest version changed",
    )
    require(
        len(manifest.get("samples", [])) == len(train) + len(validation),
        "formal manifest count changed",
    )

    base_rows = train + validation
    family_split: dict[str, str] = {}
    family_counts: Counter[tuple[str, str]] = Counter()
    for row in base_rows:
        family = row["repo_family"]
        split = row["split"]
        require(split in {"train", "validation"}, "unexpected formal split")
        require(
            family not in family_split or family_split[family] == split,
            "base family split overlap",
        )
        family_split[family] = split
        family_counts[(split, family)] += 1
        require(family_counts[(split, family)] <= 2, "base family cap exceeded")

    holdout = read_json(paths["formal_holdout_manifest"])
    confirmation = read_json(paths["confirmation_manifest"])
    external = read_json(paths["external_manifest"])
    holdout_problems = {str(row["problem_id"]) for row in holdout["cases"]}
    confirmation_problems = {str(row["problem_id"]) for row in confirmation["cases"]}
    external_projects = {str(row["project"]).lower() for row in external["cases"]}
    require(
        len(holdout_problems) == frozen["formal_holdout_manifest"]["count"],
        "holdout identity changed",
    )
    require(
        len(confirmation_problems) == frozen["confirmation_manifest"]["count"],
        "confirmation identity changed",
    )
    require(
        len(external["cases"]) == frozen["external_manifest"]["count"],
        "external count changed",
    )
    require(external_projects == EXPECTED_EXTERNAL_PROJECTS, "external project set changed")
    require(
        not holdout_problems & confirmation_problems,
        "evaluation problem families overlap",
    )
    return {
        "paths": paths,
        "base_rows": base_rows,
        "family_split": family_split,
        "family_counts": family_counts,
        "frozen_payloads": {payload_key_from_sample(row) for row in base_rows},
        "holdout_problems": holdout_problems,
        "confirmation_problems": confirmation_problems,
        "external_projects": external_projects,
    }


def verify_raw(config: dict[str, Any]) -> tuple[Path, Path]:
    raw = config["raw"]
    commitpack = verify_file(raw["commitpackft_cpp"], "CommitPackFT raw")
    rbr = raw["runbugrun"]
    directory = Path(rbr["directory"])
    require(directory.is_dir(), f"missing RunBugRun directory: {directory}")
    record_path = directory / "source-record.json"
    require(
        sha256_file(record_path) == rbr["source_record_sha256"],
        "RunBugRun source record changed",
    )
    source_record = read_json(record_path)
    recorded = {
        row["filename"]: row["sha256"]
        for row in source_record["files"]
        if row.get("language") == "cpp"
    }
    require(recorded == rbr["files"], "RunBugRun source-record file set changed")
    for name, expected in sorted(rbr["files"].items()):
        path = directory / name
        require(path.is_file(), f"missing RunBugRun shard: {name}")
        require(sha256_file(path) == expected, f"RunBugRun shard changed: {name}")
    return commitpack, directory


def candidate_rank(candidate: dict[str, Any]) -> tuple[Any, ...]:
    priority = {
        "add_helper": 4,
        "localized_refactor": 3,
        "multi_line_local": 2,
        "single_line": 1,
    }
    return (
        -priority[candidate["edit_type"]],
        -int(candidate["code_lines"] >= 100),
        -candidate["changed_lines"],
        candidate["stable_id"],
    )


def assign_split(
    source: str,
    family: str,
    upstream_split: str,
    existing: dict[str, str],
    validation_percent: int,
    seed: int,
) -> str:
    if family in existing:
        return existing[family]
    if source == "runbugrun":
        require(
            upstream_split in {"train", "validation"},
            "unexpected RunBugRun split",
        )
        return upstream_split
    bucket = int(stable_hash(seed, family)[:8], 16) % 100
    return "validation" if bucket < validation_percent else "train"


def retain_prefilter(
    pool: dict[str, list[dict[str, Any]]],
    candidate: dict[str, Any],
    limit: int,
) -> None:
    rows = pool.setdefault(candidate["family"], [])
    rows.append(candidate)
    rows.sort(key=candidate_rank)
    del rows[limit:]


def feature_flags(row: dict[str, Any], config: dict[str, Any]) -> dict[str, bool]:
    policy = config["candidate_policy"]
    return {
        "new_family": row["new_family"],
        "code_lines_ge_100": row["code_lines"] >= policy["long_code_min_lines"],
        "prompt_tokens_ge_1024": (
            row["prompt_tokens"] >= policy["long_prompt_min_tokens"]
        ),
        "complex_edit": row["edit_type"] in policy["complex_edit_types"],
        "structural_edit": row["edit_type"] in policy["structural_edit_types"],
        "file_window": row["task_level"] == "file_window",
        "commitpackft": row["source_dataset"] == "CommitPackFT",
    }


def summarize(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "source": dict(sorted(Counter(row["source_dataset"] for row in rows).items())),
        "task_level": dict(sorted(Counter(row["task_level"] for row in rows).items())),
        "edit_type": dict(sorted(Counter(row["edit_type"] for row in rows).items())),
        "source_shard": dict(sorted(Counter(row["source_shard"] for row in rows).items())),
        "feature_counts": {
            key: sum(feature_flags(row, config)[key] for row in rows)
            for key in FEATURE_KEYS
        },
    }


def proposal_score(row: dict[str, Any], config: dict[str, Any]) -> tuple[Any, ...]:
    flags = feature_flags(row, config)
    score = (
        6 * flags["structural_edit"]
        + 4 * flags["prompt_tokens_ge_1024"]
        + 4 * flags["code_lines_ge_100"]
        + 3 * flags["complex_edit"]
        + 2 * flags["new_family"]
        + 2 * flags["file_window"]
        + flags["commitpackft"]
    )
    return (-score, row["stable_id"])


def select_proposal(
    rows: list[dict[str, Any]],
    split: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    total = config["provisional_increment"][split]["total"]
    eligible_rows = [row for row in rows if row["split"] == split]
    return sorted(eligible_rows, key=lambda row: proposal_score(row, config))[:total]


def target_report(
    rows: list[dict[str, Any]],
    split: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    target = config["provisional_increment"][split]
    actual = {"total": len(rows), **summarize(rows, config)["feature_counts"]}
    mapping = {
        "minimum_new_family": "new_family",
        "minimum_code_lines_ge_100": "code_lines_ge_100",
        "minimum_prompt_tokens_ge_1024": "prompt_tokens_ge_1024",
        "minimum_complex_edit": "complex_edit",
        "minimum_structural_edit": "structural_edit",
        "minimum_file_window": "file_window",
        "minimum_commitpackft": "commitpackft",
    }
    checks = {"total": actual["total"] >= target["total"]}
    for target_key, actual_key in mapping.items():
        checks[target_key] = actual[actual_key] >= target[target_key]
    return {
        "target": target,
        "actual": actual,
        "checks": checks,
        "all_passed": all(checks.values()),
        "selection_note": (
            "deterministic composite-priority proposal; "
            "checks are simultaneous on this proposal"
        ),
    }


def base_metrics(
    rows: list[dict[str, Any]], tokenizer: Any, config: dict[str, Any]
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        encoded = encode_example(
            tokenizer, row, config["candidate_policy"]["max_sequence_tokens"]
        )
        result.append({
            "source_dataset": row["source_dataset"],
            "source_shard": "frozen-v1",
            "split": row["split"],
            "new_family": False,
            "task_level": row["task_level"],
            "edit_type": row["edit_type"],
            "code_lines": len(row["context"]["buggy_code"].splitlines()),
            "prompt_tokens": encoded["prompt_tokens"],
        })
    return result


def audit(
    config: dict[str, Any],
    *,
    include_samples: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    validate_config(config)
    frozen = load_frozen_state(config)
    commitpack, runbugrun = verify_raw(config)
    model = config["model"]
    model_path = Path(model["local_path"])
    require(model_path.is_dir(), "model directory missing")
    require(
        sha256_file(model_path / "config.json") == model["config_sha256"],
        "model config changed",
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    isolation = config["isolation"]
    max_per_family = isolation[
        "maximum_samples_per_family_across_v1_plus_increment"
    ]
    rejects: Counter[str] = Counter()
    raw_seen: Counter[str] = Counter()
    pool: dict[str, list[dict[str, Any]]] = {}
    seen_payloads = set(frozen["frozen_payloads"])
    seen_source_ids: set[tuple[str, str]] = set()

    for source, path in (
        ("commitpackft", commitpack),
        ("runbugrun", runbugrun),
    ):
        for record in iter_records(path, source):
            raw_seen[source] += 1
            ok, reason, info = eligible(record)
            if not ok:
                rejects[f"{source}:{reason}"] += 1
                continue
            family = info["family"]
            problem = str(record.get("problem_id", ""))
            if source == "runbugrun" and problem in frozen["holdout_problems"]:
                rejects["runbugrun:formal_holdout_family"] += 1
                continue
            if source == "runbugrun" and problem in frozen["confirmation_problems"]:
                rejects["runbugrun:confirmation_family"] += 1
                continue
            if source == "commitpackft" and matches_external_alias(
                family, isolation["exclude_external_repository_aliases"]
            ):
                rejects["commitpackft:external_repository_alias"] += 1
                continue
            source_identity = (source, source_key(record))
            if source_identity in seen_source_ids:
                rejects[f"{source}:duplicate_source_id"] += 1
                continue
            item = {"record": record, "info": info}
            payload = payload_key_from_item(item)
            if payload in seen_payloads:
                rejects[f"{source}:frozen_or_duplicate_payload"] += 1
                continue
            existing_split = frozen["family_split"].get(family)
            split = assign_split(
                source,
                family,
                record["_upstream_split"],
                frozen["family_split"],
                isolation[
                    "commitpack_validation_percent_for_new_families"
                ],
                config["seed"],
            )
            if (
                source == "runbugrun"
                and existing_split
                and split != record["_upstream_split"]
            ):
                rejects[
                    "runbugrun:upstream_split_conflicts_with_base"
                ] += 1
                continue
            if frozen["family_counts"][(split, family)] >= max_per_family:
                rejects[f"{source}:family_cap_filled_by_v1"] += 1
                continue
            level = formal_level(info["old"], info["filename"], info["new"])
            edit_type = classify_edit(info["old"], info["new"], info["changed"])
            candidate = {
                "family": family,
                "source": source,
                "source_dataset": (
                    "RunBugRun" if source == "runbugrun" else "CommitPackFT"
                ),
                "source_shard": record["_shard"],
                "payload_hash": payload,
                "record": record,
                "info": {**info, "level": level, "edit_type": edit_type},
                "split": split,
                "task_level": level,
                "edit_type": edit_type,
                "changed_lines": info["changed"],
                "code_lines": len(info["old"].splitlines()),
                "new_family": family not in frozen["family_split"],
                "stable_id": stable_hash(
                    config["seed"], source, family, source_key(record), payload
                ),
            }
            retain_prefilter(
                pool,
                candidate,
                isolation["prefilter_candidates_per_family"],
            )
            seen_payloads.add(payload)
            seen_source_ids.add(source_identity)

    available: list[dict[str, Any]] = []
    token_rejects: Counter[str] = Counter()
    for family in sorted(pool, key=lambda value: stable_hash(config["seed"], value)):
        existing_split = frozen["family_split"].get(family)
        base_count = (
            frozen["family_counts"][(existing_split, family)]
            if existing_split is not None
            else 0
        )
        remaining = max_per_family - base_count
        chosen = 0
        for candidate in sorted(pool[family], key=candidate_rank):
            if chosen >= remaining:
                break
            sample = make_sample(
                {"record": candidate["record"], "info": candidate["info"]},
                candidate["split"],
                len(available),
            )
            sample["task_level"] = candidate["task_level"]
            sample["edit_type"] = candidate["edit_type"]
            try:
                encoded = encode_example(
                    tokenizer,
                    sample,
                    config["candidate_policy"]["max_sequence_tokens"],
                )
            except RuntimeError:
                token_rejects[
                    f"{candidate['source']}:{candidate['split']}:sequence_over_limit"
                ] += 1
                continue
            projected = {
                "candidate_id": f"dv2-{candidate['stable_id'][:24]}",
                "stable_id": candidate["stable_id"],
                "source_dataset": candidate["source_dataset"],
                "source_shard": candidate["source_shard"],
                "split": candidate["split"],
                "family_hash": "sha256:"
                + hashlib.sha256(family.encode("utf-8")).hexdigest(),
                "source_id_hash": "sha256:"
                + hashlib.sha256(
                    source_key(candidate["record"]).encode("utf-8")
                ).hexdigest(),
                "payload_hash": candidate["payload_hash"],
                "new_family": candidate["new_family"],
                "task_level": candidate["task_level"],
                "edit_type": candidate["edit_type"],
                "changed_lines": candidate["changed_lines"],
                "code_lines": candidate["code_lines"],
                "prompt_tokens": encoded["prompt_tokens"],
                "target_tokens": encoded["target_tokens"],
                "sequence_tokens": encoded["sequence_tokens"],
            }
            if include_samples:
                projected["_sample"] = sample
            available.append(projected)
            chosen += 1

    proposals = {
        split: select_proposal(available, split, config)
        for split in ("train", "validation")
    }
    summary = {
        "version": VERSION,
        "status": "feasibility_only_no_training_data_created",
        "raw_records_seen": dict(sorted(raw_seen.items())),
        "base": summarize(base_metrics(frozen["base_rows"], tokenizer, config), config),
        "available_increment": {
            split: summarize(
                [row for row in available if row["split"] == split],
                config,
            )
            for split in ("train", "validation")
        },
        "provisional_proposal": {
            split: {
                "summary": summarize(proposals[split], config),
                "target_report": target_report(
                    proposals[split], split, config
                ),
            }
            for split in ("train", "validation")
        },
        "pre_token_rejections": dict(sorted(rejects.items())),
        "token_rejections": dict(sorted(token_rejects.items())),
        "evaluation_isolation": {
            "formal_holdout_problem_families_excluded": len(
                frozen["holdout_problems"]
            ),
            "confirmation_problem_families_excluded": len(
                frozen["confirmation_problems"]
            ),
            "external_projects_excluded": sorted(
                frozen["external_projects"]
            ),
            "confirmation_or_external_gold_consumed": False,
            "evaluation_fields_consumed": isolation[
                "evaluation_fields_consumed"
            ],
        },
        "interpretation_boundary": [
            "Availability is measured after exact tokenization and the combined v1+increment family cap.",
            "The proposal is a deterministic feasibility sample, not a frozen Data-v2 training set.",
            "No confirmation/external source, patch, test, score, or gold field is read.",
            "CommitPackFT remains non-executable SFT evidence unless a separate repository replay layer is built.",
        ],
    }
    manifest = {
        "version": VERSION,
        "config_sha256": None,
        "model": {
            "model_id": model["model_id"],
            "revision": model["revision"],
            "config_sha256": model["config_sha256"],
        },
        "input_sha256": {
            **{
                name: spec["sha256"]
                for name, spec in config["frozen_inputs"].items()
            },
            "commitpackft_cpp": config["raw"]["commitpackft_cpp"]["sha256"],
            "runbugrun_source_record": config["raw"]["runbugrun"][
                "source_record_sha256"
            ],
            **{
                f"runbugrun/{name}": value
                for name, value in config["raw"]["runbugrun"]["files"].items()
            },
        },
        "candidate_count": len(available),
        "proposal_candidate_ids": {
            split: [row["candidate_id"] for row in proposals[split]]
            for split in ("train", "validation")
        },
    }
    return summary, available, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config = read_json(args.config)
    summary, available, manifest = audit(config)
    output = (args.output_dir or Path(config["output_dir"])).resolve()
    require(not output.exists(), f"refusing to overwrite output: {output}")
    output.mkdir(parents=True)
    manifest["config_sha256"] = sha256_file(args.config)
    with (output / "candidate-audit.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        for row in sorted(available, key=lambda value: value["candidate_id"]):
            stream.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )
    write_json(output / "summary.json", summary)
    manifest["git_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    manifest["output_sha256"] = {
        "candidate-audit.jsonl": sha256_file(
            output / "candidate-audit.jsonl"
        ),
        "summary.json": sha256_file(output / "summary.json"),
    }
    manifest["created_at"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps({
        "output": str(output),
        "available": {
            split: summary["available_increment"][split]["count"]
            for split in ("train", "validation")
        },
        "proposal_passed": {
            split: summary["provisional_proposal"][split][
                "target_report"
            ]["all_passed"]
            for split in ("train", "validation")
        },
        "sha256": {
            name: sha256_file(output / name)
            for name in (
                "candidate-audit.jsonl",
                "summary.json",
                "run-manifest.json",
            )
        },
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
