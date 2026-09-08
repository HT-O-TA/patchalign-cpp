#!/usr/bin/env python3
"""Audit one frozen CommitPack C++ shard without emitting source or training data."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Iterable, Mapping

VERSION = "data-v2-commitpack-shard-audit-v1"
SHA_RE = re.compile(r"[0-9a-f]{40}")
REPO_PART_RE = re.compile(r"[A-Za-z0-9_.-]+")
LICENSE_ALIASES = {
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsl-1.0": "BSL-1.0",
    "isc": "ISC",
    "mit": "MIT",
    "zlib": "Zlib",
}
FUNCTION_PATTERN = re.compile(
    r"(?m)^[^#\n;{}]*?\b([A-Za-z_]\w*)\s*"
    r"\([^;{}]*\)\s*(?:const\s*)?\{"
)
CONTROL_NAMES = {"if", "for", "while", "switch", "catch"}


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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def stable_hash(*values: object) -> str:
    return hashlib.sha256(canonical_json(values)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def verify_file(spec: Mapping[str, Any], label: str) -> Path:
    path = Path(str(spec["path"]))
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    if "bytes" in spec:
        require(path.stat().st_size == int(spec["bytes"]), f"{label} byte size changed")
    return path


def normalize_license(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return LICENSE_ALIASES.get(value.strip().lower())


def canonical_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return str(path)


def canonical_repository(value: object, *, require_single: bool = True) -> str | None:
    if not isinstance(value, str):
        return None
    entries = [item.strip() for item in value.split(",") if item.strip()]
    if not entries or (require_single and len(entries) != 1):
        return None
    raw = entries[0].strip().rstrip("/")
    raw = re.sub(r"^(?:https?://)?github\.com/", "", raw, flags=re.IGNORECASE)
    raw = raw.removesuffix(".git")
    parts = raw.split("/")
    if len(parts) != 2 or not all(REPO_PART_RE.fullmatch(part) for part in parts):
        return None
    return f"github.com/{parts[0].lower()}/{parts[1].lower()}"


def content_pair_hash(old: str, new: str) -> str:
    return stable_hash(old, new)


def changed_analysis(old: str, new: str) -> tuple[int, list[int], str]:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=True)
    additions = 0
    deletions = 0
    changed_old_lines: list[int] = []
    anchors: list[object] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        deletions += i2 - i1
        additions += j2 - j1
        changed_old_lines.extend(range(i1 + 1, i2 + 1))
        anchors.append(
            [
                tag,
                old_lines[max(0, i1 - 1) : min(len(old_lines), i2 + 1)],
                new_lines[max(0, j1 - 1) : min(len(new_lines), j2 + 1)],
            ]
        )
    return max(additions, deletions), changed_old_lines, stable_hash(anchors)


def heuristic_task_level(old: str, changed_old_lines: list[int]) -> str:
    containing = [
        span
        for span in function_spans(old)
        if changed_old_lines
        and all(span[0] <= line <= span[1] for line in changed_old_lines)
    ]
    return "function" if containing else "file_window"


def keyword_match(subject: str, message: str, terms: Iterable[str]) -> bool:
    text = f"{subject}\n{message}".casefold()
    tokens = set(re.findall(r"[a-z0-9_]+", text))
    stems = set(terms)
    if tokens & stems:
        return True
    return any(
        token.startswith(("fix", "bug", "crash", "fail", "regress"))
        for token in tokens
    )


def normalized_component(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def repository_is_denied(repository: str, denylist: Mapping[str, Any]) -> bool:
    matching = denylist["repository_matching"]
    if repository in {value.casefold() for value in matching["exact_canonical_repositories"]}:
        return True
    repository_name = normalized_component(repository.rsplit("/", 1)[-1])
    aliases = {
        normalized_component(value)
        for value in matching["normalized_repository_name_aliases"]
    }
    if any(alias and alias in repository_name for alias in aliases):
        return True
    components = [normalized_component(part) for part in repository.split("/")]
    return any(
        normalized_component(token) in component
        for token in matching["exclude_if_any_normalized_component_contains"]
        for component in components
    )


def assign_split(repository: str, existing: Mapping[str, str], seed: int, percent: int) -> str:
    if repository in existing:
        return existing[repository]
    bucket = int(stable_hash(seed, repository)[:8], 16) % 100
    return "validation" if bucket < percent else "train"


def sampling_family(repository: str, path: str, anchor_hash: str) -> str:
    return f"{repository}|{path}|{anchor_hash}"


def candidate_rank(row: Mapping[str, Any]) -> tuple[Any, ...]:
    edit_priority = {
        "add_helper": 4,
        "localized_refactor": 3,
        "multi_line_local": 2,
        "single_line": 1,
    }
    return (
        -int(row["bug_keyword"]),
        -edit_priority[str(row["edit_type"])],
        -int(row["long_code"]),
        -int(row["long_prompt_estimate"]),
        -int(row["task_level"] == "function"),
        -int(row["changed_logical_lines"]),
        str(row["stable_id"]),
    )


def retain_best(pool: dict[str, list[dict[str, Any]]], key: str, row: dict[str, Any], limit: int) -> None:
    rows = pool.setdefault(key, [])
    rows.append(row)
    rows.sort(key=candidate_rank)
    del rows[limit:]


def read_jsonl_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        for number, line in enumerate(stream, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"invalid JSON at {path}:{number}: {error}") from error
            require(isinstance(value, dict), f"non-object JSON at {path}:{number}")
            yield value


def patch_anchor_hash(patch: str) -> str:
    changed = [
        line
        for line in patch.splitlines()
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    ]
    return stable_hash(changed)


def load_frozen_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    split_by_repo: dict[str, str] = {}
    used_source_identities: set[tuple[str, str]] = set()
    frozen_family_counts: Counter[str] = Counter()
    frozen_repositories: set[str] = set()
    for split in ("train", "validation"):
        spec = config["frozen_sft"][split]
        path = verify_file(spec, f"frozen SFT {split}")
        count = 0
        for row in read_jsonl_rows(path):
            count += 1
            repository = canonical_repository(row.get("repo_id"), require_single=False)
            if repository is None:
                continue
            frozen_repositories.add(repository)
            prior = split_by_repo.setdefault(repository, split)
            require(prior == split, f"frozen repository split overlap: {repository}")
            if row.get("source_dataset") != "CommitPackFT":
                continue
            commit = str(row.get("fix_commit", "")).casefold()
            target = canonical_path(row.get("context", {}).get("target_file"))
            patch = row.get("gold_patch")
            if SHA_RE.fullmatch(commit) and target and isinstance(patch, str):
                used_source_identities.add((repository, commit))
                family = sampling_family(repository, target, patch_anchor_hash(patch))
                frozen_family_counts[family] += 1
        require(count == spec["count"], f"frozen SFT {split} count changed")
    return {
        "split_by_repo": split_by_repo,
        "used_source_identities": used_source_identities,
        "frozen_family_counts": frozen_family_counts,
        "frozen_repositories": frozen_repositories,
    }


def load_legacy_identity(path: Path) -> dict[str, Any]:
    payloads: set[str] = set()
    commits: set[str] = set()
    paths: set[tuple[str, str, str, str]] = set()
    rows = 0
    for row in read_jsonl_rows(path):
        rows += 1
        old = row.get("old_contents")
        new = row.get("new_contents")
        commit = str(row.get("commit", "")).casefold()
        if isinstance(old, str) and isinstance(new, str):
            payloads.add(content_pair_hash(old, new))
        if SHA_RE.fullmatch(commit):
            commits.add(commit)
        repository = canonical_repository(row.get("repos"), require_single=False)
        old_path = canonical_path(row.get("old_file"))
        new_path = canonical_path(row.get("new_file"))
        if repository and old_path and new_path and SHA_RE.fullmatch(commit):
            paths.add((repository, commit, old_path, new_path))
    return {"payloads": payloads, "commits": commits, "paths": paths, "rows": rows}


def validate_config(config: Mapping[str, Any], *, verify_heavy_inputs: bool) -> dict[str, Any]:
    require(config.get("version") == VERSION, "unexpected CommitPack audit version")
    verify_file(config["decision"], "ADR-0022")
    bindings = {name: load_json(verify_file(spec, name)) for name, spec in config["bindings"].items()}
    contract = bindings["contract"]
    require(contract["version"] == "data-v2-contract-v2.1", "contract version changed")
    require(contract["caps"]["maximum_single_new_source_fraction"] == 0.7, "source cap changed")
    require(contract["split"]["hash_seed"] == 20260906, "split seed changed")
    require(contract["split"]["new_split_group_validation_percent"] == 10, "split percent changed")
    source_policy = bindings["source_admission"]
    require(
        config["license"]["allowed_spdx"]
        == source_policy["license_policy"]["initial_permissive_spdx_allowlist"],
        "license allowlist changed",
    )
    upstream = config["upstream"]
    require(upstream["dataset"] == "bigcode/commitpack", "dataset changed")
    require(upstream["revision"] == "5eee2c845bf88dbffcafedb6e80d2a72a43fe575", "revision changed")
    require(upstream["relative_path"] == "data/c++/c++-0001.jsonl", "shard changed")
    require(upstream["bytes"] == 523946192, "shard size changed")
    require(upstream["sha256"] == "sha256:dfdd55f56f7be3bf4b8d2ccad8ea39910b4dd2c18ee296f5a991d134e57f367f", "shard hash changed")
    require(upstream["additional_shards_authorized"] is False, "additional shard enabled")
    scope = config["scope"]
    require(scope["streaming_static_audit_only"] is True, "audit scope changed")
    require(scope["training_data_created"] is False, "training enabled")
    require(scope["gpu_authorized"] is False, "GPU enabled")
    require(scope["dpo_authorized"] is False, "DPO enabled")
    identity = config["identity"]
    require(identity["maximum_samples_per_sampling_family_across_v1_plus_increment"] == 2, "family cap changed")
    require(identity["maximum_increment_per_repository"] == {"train": 40, "validation": 20}, "repository cap changed")
    require(config["static_share_gate"]["train"] == {"samples": 1400, "new_repositories": 100, "sampling_families": 700}, "train share gate changed")
    require(config["static_share_gate"]["validation"] == {"samples": 140, "new_repositories": 20, "sampling_families": 70}, "validation share gate changed")
    require(config["known_supply"]["minimum_remaining_independent_train_after_commitpack_cap"] == 340, "remaining-source arithmetic changed")
    if verify_heavy_inputs:
        verify_file(config["legacy_commitpackft"], "legacy CommitPackFT")
        for split in ("train", "validation"):
            verify_file(config["frozen_sft"][split], f"frozen SFT {split}")
    return bindings


def project_candidate(
    row: Mapping[str, Any],
    config: Mapping[str, Any],
    frozen: Mapping[str, Any],
    denylist: Mapping[str, Any],
    legacy: Mapping[str, set[Any]],
    seen: dict[str, set[Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    schema = config["schema"]
    required = set(schema["required_fields"])
    if not required.issubset(row):
        return None, "schema_missing_fields"
    if row.get("lang") != schema["language"]:
        return None, "language_mismatch"
    repository = canonical_repository(row.get("repos"), require_single=True)
    if repository is None:
        return None, "repository_not_single_or_invalid"
    commit = str(row.get("commit", "")).casefold()
    if SHA_RE.fullmatch(commit) is None:
        return None, "commit_not_40_hex"
    old_path = canonical_path(row.get("old_file"))
    new_path = canonical_path(row.get("new_file"))
    if old_path is None or new_path is None:
        return None, "invalid_path"
    extensions = set(schema["cpp_extensions"])
    if PurePosixPath(old_path).suffix.casefold() not in extensions or PurePosixPath(new_path).suffix.casefold() not in extensions:
        return None, "non_cpp_path"
    old = row.get("old_contents")
    new = row.get("new_contents")
    if not isinstance(old, str) or not isinstance(new, str) or not old or not new:
        return None, "missing_contents"
    if old == new:
        return None, "unchanged_contents"
    license_id = normalize_license(row.get("license"))
    if license_id not in set(config["license"]["allowed_spdx"]):
        return None, "license_not_allowlisted"
    if repository_is_denied(repository, denylist):
        return None, "evaluation_repository_denylist"
    payload_hash = content_pair_hash(old, new)
    path_identity = (repository, commit, old_path, new_path)
    if payload_hash in legacy["payloads"]:
        return None, "legacy_payload_duplicate"
    if commit in legacy["commits"]:
        return None, "legacy_commit_duplicate"
    if path_identity in legacy["paths"]:
        return None, "legacy_path_identity_duplicate"
    if payload_hash in seen["payloads"]:
        return None, "shard_payload_duplicate"
    if commit in seen["commits"]:
        return None, "shard_commit_duplicate"
    if path_identity in seen["paths"]:
        return None, "shard_path_identity_duplicate"
    changed, changed_old_lines, anchor_hash = changed_analysis(old, new)
    if not schema["minimum_changed_logical_lines"] <= changed <= schema["maximum_changed_logical_lines"]:
        return None, "changed_lines_out_of_range"
    subject = row.get("subject") if isinstance(row.get("subject"), str) else ""
    message = row.get("message") if isinstance(row.get("message"), str) else ""
    family = sampling_family(repository, new_path, anchor_hash)
    family_used = int(frozen["frozen_family_counts"].get(family, 0))
    remaining = config["identity"]["maximum_samples_per_sampling_family_across_v1_plus_increment"] - family_used
    if remaining <= 0:
        return None, "sampling_family_filled_by_v1"
    split = assign_split(
        repository,
        frozen["split_by_repo"],
        config["identity"]["split_seed"],
        config["identity"]["new_repository_validation_percent"],
    )
    task_level = heuristic_task_level(old, changed_old_lines)
    edit_type = classify_edit(old, new, changed)
    estimated_prompt_tokens = max(1, (len(old.encode("utf-8")) + len(subject.encode("utf-8")) + 512) // 4)
    stable_id = stable_hash(repository, commit, old_path, new_path, payload_hash)
    projected = {
        "candidate_id": f"cp-{stable_id[:24]}",
        "stable_id": stable_id,
        "repository_hash": "sha256:" + hashlib.sha256(repository.encode()).hexdigest(),
        "repository": repository,
        "commit": commit,
        "path_hash": "sha256:" + hashlib.sha256(new_path.encode()).hexdigest(),
        "sampling_family": family,
        "sampling_family_hash": "sha256:" + hashlib.sha256(family.encode()).hexdigest(),
        "payload_hash": "sha256:" + payload_hash,
        "split": split,
        "new_repository": repository not in frozen["frozen_repositories"],
        "license": license_id,
        "bug_keyword": keyword_match(subject, message, config["features"]["bug_fix_terms"]),
        "task_level": task_level,
        "edit_type": edit_type,
        "changed_logical_lines": changed,
        "code_lines": len(old.splitlines()),
        "estimated_full_file_prompt_tokens": estimated_prompt_tokens,
        "long_code": len(old.splitlines()) >= config["features"]["long_code_min_lines"],
        "long_prompt_estimate": estimated_prompt_tokens >= config["features"]["long_prompt_min_estimated_tokens"],
        "renamed_path": old_path != new_path,
        "family_remaining": remaining,
    }
    seen["payloads"].add(payload_hash)
    seen["commits"].add(commit)
    seen["paths"].add(path_identity)
    return projected, None


def public_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "candidate_id", "stable_id", "repository_hash", "path_hash",
        "sampling_family_hash", "payload_hash", "split", "new_repository",
        "license", "bug_keyword", "task_level", "edit_type",
        "changed_logical_lines", "code_lines", "estimated_full_file_prompt_tokens",
        "long_code", "long_prompt_estimate", "renamed_path",
    )
    return {key: row[key] for key in allowed}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "samples": len(rows),
        "repositories": len({row["repository"] for row in rows}),
        "new_repositories": len({row["repository"] for row in rows if row["new_repository"]}),
        "sampling_families": len({row["sampling_family"] for row in rows}),
        "bug_keyword": sum(row["bug_keyword"] for row in rows),
        "task_level": dict(sorted(Counter(row["task_level"] for row in rows).items())),
        "edit_type": dict(sorted(Counter(row["edit_type"] for row in rows).items())),
        "license": dict(sorted(Counter(row["license"] for row in rows).items())),
        "long_code": sum(row["long_code"] for row in rows),
        "long_prompt_estimate": sum(row["long_prompt_estimate"] for row in rows),
        "complex_edit": sum(row["edit_type"] in {"multi_line_local", "add_helper", "localized_refactor"} for row in rows),
        "structural_edit": sum(row["edit_type"] in {"add_helper", "localized_refactor"} for row in rows),
        "file_window": sum(row["task_level"] == "file_window" for row in rows),
        "renamed_path": sum(row["renamed_path"] for row in rows),
    }


def share_gate(rows: list[dict[str, Any]], split: str, config: Mapping[str, Any]) -> dict[str, Any]:
    actual = summarize(rows)
    target = config["static_share_gate"][split]
    checks = {
        "samples": actual["samples"] >= target["samples"],
        "new_repositories": actual["new_repositories"] >= target["new_repositories"],
        "sampling_families": actual["sampling_families"] >= target["sampling_families"],
    }
    return {"target": target, "actual": actual, "checks": checks, "all_passed": all(checks.values())}


def audit(config: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    bindings = validate_config(config, verify_heavy_inputs=True)
    shard_spec = {"path": config["upstream"]["local_path"], "sha256": config["upstream"]["sha256"], "bytes": config["upstream"]["bytes"]}
    shard = verify_file(shard_spec, "CommitPack shard")
    legacy_path = Path(config["legacy_commitpackft"]["path"])
    frozen = load_frozen_identity(config)
    legacy = load_legacy_identity(legacy_path)
    denylist = bindings["evaluation_denylist"]
    rejects: Counter[str] = Counter()
    raw_rows = 0
    family_pool: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[Any]] = {"payloads": set(), "commits": set(), "paths": set()}
    for row in read_jsonl_rows(shard):
        raw_rows += 1
        candidate, reason = project_candidate(row, config, frozen, denylist, legacy, seen)
        if candidate is None:
            rejects[str(reason)] += 1
            continue
        retain_best(family_pool, candidate["sampling_family"], candidate, candidate["family_remaining"])
    after_family = [row for rows in family_pool.values() for row in rows]
    repository_pool: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in after_family:
        repository_pool[(row["split"], row["repository"])].append(row)
    capped: list[dict[str, Any]] = []
    repository_cap_rejections = 0
    for (split, _), rows in repository_pool.items():
        ordered = sorted(rows, key=candidate_rank)
        cap = config["identity"]["maximum_increment_per_repository"][split]
        capped.extend(ordered[:cap])
        repository_cap_rejections += max(0, len(ordered) - cap)
    capped.sort(key=lambda row: row["stable_id"])
    require(len({row["stable_id"] for row in capped}) == len(capped), "duplicate capped candidate identity")
    split_rows = {split: [row for row in capped if row["split"] == split] for split in ("train", "validation")}
    gates = {split: share_gate(split_rows[split], split, config) for split in ("train", "validation")}
    gate_passed = all(value["all_passed"] for value in gates.values())
    known = config["known_supply"]
    combined_upper = {
        split: known["safe_legacy_increment"][split] + min(len(split_rows[split]), config["static_share_gate"][split]["samples"])
        for split in ("train", "validation")
    }
    remaining = {
        split: max(0, known["provisional_increment"][split] - combined_upper[split])
        for split in ("train", "validation")
    }
    identity_hash = "sha256:" + hashlib.sha256(
        b"".join((row["stable_id"] + "\n").encode() for row in capped)
    ).hexdigest()
    summary = {
        "version": VERSION,
        "status": "static_supply_audit_only",
        "raw_records_seen": raw_rows,
        "legacy_commitpackft_records_seen": legacy["rows"],
        "pre_cap_qualified": len(after_family),
        "repository_cap_rejections": repository_cap_rejections,
        "reject_counts": dict(sorted(rejects.items())),
        "available_after_family_and_repository_caps": {split: summarize(split_rows[split]) for split in ("train", "validation")},
        "bug_keyword_subset": {split: summarize([row for row in split_rows[split] if row["bug_keyword"]]) for split in ("train", "validation")},
        "static_share_gate": gates,
        "static_share_gate_passed": gate_passed,
        "known_supply_arithmetic": {
            "safe_legacy_increment": known["safe_legacy_increment"],
            "github_executable": known["github_executable"],
            "commitpack_maximum_allowed_contribution": {split: config["static_share_gate"][split]["samples"] for split in ("train", "validation")},
            "combined_upper_bound_before_fourth_source": combined_upper,
            "remaining_independent_source_minimum": remaining,
        },
        "candidate_identity_set_sha256_lf": identity_hash,
        "decision": {
            "fixed_repository_execution_pilot_authorized": gate_passed,
            "training_authorized": False,
            "gpu_authorized": False,
            "additional_commitpack_shards_authorized": False,
            "independent_source_still_required": True,
            "next_action": (
                "freeze a fixed repository/commit execution pilot and independently source the remaining train gap"
                if gate_passed
                else "close CommitPack after this fixed shard and investigate a genuinely independent executable source"
            ),
        },
        "interpretation_boundary": [
            "Dataset license metadata is only a static supply signal; historical repository LICENSE must be rechecked before admission.",
            "Bug-fix keywords are a reported stratum, never execution evidence.",
            "Task level and prompt length are source-text heuristics until checkout/AST/tokenizer reconstruction.",
            "No evaluation gold, repository checkout, third-party build, training example, GPU, or DPO operation was used.",
            "A pass can authorize only a fixed execution pilot; it cannot authorize training.",
        ],
    }
    manifest = {
        "version": VERSION,
        "git_commit": current_commit(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "config_sha256": None,
        "input_sha256": {
            "commitpack_shard": config["upstream"]["sha256"],
            "legacy_commitpackft": config["legacy_commitpackft"]["sha256"],
            **{name: spec["sha256"] for name, spec in config["bindings"].items()},
            **{f"frozen_sft_{split}": config["frozen_sft"][split]["sha256"] for split in ("train", "validation")},
        },
        "raw_records_seen": raw_rows,
        "candidate_count": len(capped),
        "candidate_identity_set_sha256_lf": identity_hash,
        "output_sha256": {},
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return summary, [public_projection(row) for row in capped], manifest


def current_commit() -> str:
    value = os.environ.get("PATCHALIGN_GIT_COMMIT", "").strip()
    if not value:
        value = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(SHA_RE.fullmatch(value) is not None, "invalid Git commit")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/data/data_v2_commitpack_shard_audit_v1.json"))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)
    validate_config(config, verify_heavy_inputs=args.preflight_only)
    if args.preflight_only:
        print(json.dumps({"status": "preflight_passed", "version": VERSION}, sort_keys=True))
        return
    summary, candidates, manifest = audit(config)
    output = Path(config["output_directory"])
    require(not output.exists(), f"refusing to overwrite output: {output}")
    output.mkdir(parents=True)
    candidate_path = output / "candidate-audit.jsonl"
    with candidate_path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in candidates:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    write_json(output / "summary.json", summary)
    manifest["config_sha256"] = sha256_file(args.config)
    manifest["output_sha256"] = {
        "candidate-audit.jsonl": sha256_file(candidate_path),
        "summary.json": sha256_file(output / "summary.json"),
    }
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps({
        "output": str(output),
        "raw_records_seen": summary["raw_records_seen"],
        "available": {split: summary["available_after_family_and_repository_caps"][split]["samples"] for split in ("train", "validation")},
        "static_share_gate_passed": summary["static_share_gate_passed"],
        "sha256": {name: sha256_file(output / name) for name in ("candidate-audit.jsonl", "summary.json", "run-manifest.json")},
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
