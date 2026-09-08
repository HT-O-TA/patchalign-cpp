#!/usr/bin/env python3
"""Audit fixed BeetleBox Parquet metadata without reading issue text or source."""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from scripts.data.audit_data_v2_commitpack_shard import (
    assign_split,
    repository_is_denied,
)


VERSION = "data-v2-beetlebox-metadata-audit-v1"
SHA_RE = re.compile(r"[0-9a-f]{40}")
REPO_PART_RE = re.compile(r"[A-Za-z0-9_.-]+")


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


def canonical_repository(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().rstrip("/").removesuffix(".git")
    raw = re.sub(r"^(?:https?://)?github\.com/", "", raw, flags=re.IGNORECASE)
    parts = raw.split("/")
    if len(parts) != 2 or not all(REPO_PART_RE.fullmatch(part) for part in parts):
        return None
    return f"github.com/{parts[0].lower()}/{parts[1].lower()}"


def canonical_github_record_url(value: object, repository: str, kind: str) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com":
        return False
    parts = [part for part in parsed.path.split("/") if part]
    expected = repository.split("/")[1:]
    return (
        len(parts) == 4
        and [part.casefold() for part in parts[:2]] == expected
        and parts[2] == kind
        and parts[3].isdigit()
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _paths_from_value(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        direct = value.get("filename") or value.get("path") or value.get("file")
        if isinstance(direct, str):
            return [direct]
        paths: list[str] = []
        for key, item in value.items():
            if isinstance(key, str) and "/" in key:
                paths.append(key)
            paths.extend(_paths_from_value(item))
        return paths
    if isinstance(value, (list, tuple, set)):
        paths: list[str] = []
        for item in value:
            paths.extend(_paths_from_value(item))
        return paths
    return []


def parse_updated_files(value: object) -> list[str] | None:
    parsed = value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(raw)
                break
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
        else:
            return None
    paths: list[str] = []
    for raw_path in _paths_from_value(parsed):
        if not raw_path or "\\" in raw_path or "\x00" in raw_path:
            continue
        path = PurePosixPath(raw_path)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            continue
        paths.append(str(path))
    return sorted(set(paths)) or None


def datetime_value(value: object) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def project_record(
    row: Mapping[str, Any],
    config: Mapping[str, Any],
    denylist: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    schema = config["schema"]
    if row.get("language") != schema["language_value"]:
        return None, "language_mismatch"
    repository = canonical_repository(row.get("repo_name"))
    url_repository = canonical_repository(row.get("repo_url"))
    if repository is None or url_repository != repository:
        return None, "repository_invalid_or_mismatch"
    before = row.get("before_fix_sha")
    after = row.get("after_fix_sha")
    if not isinstance(before, str) or not SHA_RE.fullmatch(before):
        return None, "before_sha_invalid"
    if not isinstance(after, str) or not SHA_RE.fullmatch(after):
        return None, "after_sha_invalid"
    if before == after:
        return None, "identical_before_after_sha"
    issue_id = row.get("issue_id")
    if not isinstance(issue_id, int) or isinstance(issue_id, bool) or issue_id <= 0:
        return None, "issue_id_invalid"
    if not canonical_github_record_url(row.get("issue_url"), repository, "issues"):
        return None, "issue_url_invalid"
    if not canonical_github_record_url(row.get("pull_url"), repository, "pull"):
        return None, "pull_url_invalid"
    paths = parse_updated_files(row.get("updated_files"))
    if paths is None:
        return None, "updated_files_invalid"
    cpp_extensions = {value.casefold() for value in schema["cpp_extensions"]}
    cpp_paths = [path for path in paths if PurePosixPath(path).suffix.casefold() in cpp_extensions]
    if not cpp_paths:
        return None, "no_cpp_updated_file"
    report_time = datetime_value(row.get("report_datetime"))
    commit_time = datetime_value(row.get("commit_datetime"))
    if report_time is None or commit_time is None:
        return None, "timestamp_invalid"
    if repository_is_denied(repository, denylist):
        return None, "evaluation_repository_denylist"
    identity = stable_hash(repository, before, after, issue_id)
    return {
        "stable_id": identity,
        "repository": repository,
        "before": before,
        "after": after,
        "issue_id": issue_id,
        "updated_file_count": len(paths),
        "cpp_file_count": len(cpp_paths),
        "report_time": report_time,
        "commit_time": commit_time,
    }, None


def cap_and_gate(candidates: Iterable[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, Any]:
    identity = config["identity"]
    by_split_repo: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        "train": defaultdict(list),
        "validation": defaultdict(list),
    }
    for candidate in candidates:
        repository = str(candidate["repository"])
        split = assign_split(
            repository,
            {},
            int(identity["repository_resplit_seed"]),
            int(identity["validation_percent"]),
        )
        by_split_repo[split][repository].append(candidate)

    result: dict[str, Any] = {}
    for split in ("train", "validation"):
        cap = int(identity["maximum_increment_per_repository"][split])
        retained: list[Mapping[str, Any]] = []
        for repository in sorted(by_split_repo[split]):
            rows = sorted(by_split_repo[split][repository], key=lambda row: str(row["stable_id"]))
            retained.extend(rows[:cap])
        target = config["metadata_gate"][split]
        actual = {
            "samples_after_cap": len(retained),
            "repositories": len({str(row["repository"]) for row in retained}),
        }
        checks = {key: actual[key] >= int(value) for key, value in target.items()}
        result[split] = {
            "actual": actual,
            "target": target,
            "checks": checks,
            "all_passed": all(checks.values()),
        }
    result["all_passed"] = result["train"]["all_passed"] and result["validation"]["all_passed"]
    return result


def iter_parquet_rows(path: Path, columns: list[str]) -> Iterable[dict[str, Any]]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(columns=columns, batch_size=2048):
        yield from batch.to_pylist()


def verify_config(config: Mapping[str, Any], *, require_files: bool) -> None:
    require(config.get("version") == VERSION, "unexpected config version")
    scope = config["scope"]
    require(scope["fixed_metadata_download_authorized"] is True, "metadata download not authorized")
    for key in (
        "title_or_body_read", "source_or_patch_download_authorized",
        "repository_checkout_authorized", "training_data_created", "gpu_authorized",
        "dpo_authorized", "evaluation_gold_consumed",
    ):
        require(scope[key] is False, f"unsafe scope flag enabled: {key}")
    prohibited = set(config["schema"]["prohibited_read_columns"])
    require(not prohibited & set(config["schema"]["read_columns"]), "prohibited columns requested")
    require(config["identity"]["native_split_is_not_training_split"] is True, "native split reuse enabled")
    require(config["reporting"]["emit_repository_names"] is False, "repository names would be emitted")
    require(config["metadata_gate"]["pass_authorizes_content_download"] is False, "content auto-authorization enabled")
    require(config["metadata_gate"]["pass_authorizes_training"] is False, "training auto-authorization enabled")
    for label in ("decision",):
        spec = config[label]
        path = Path(str(spec["path"]))
        require(path.is_file(), f"missing {label}: {path}")
        require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    for label, spec in config["bindings"].items():
        path = Path(str(spec["path"]))
        require(path.is_file(), f"missing binding {label}: {path}")
        require(sha256_file(path) == spec["sha256"], f"binding hash changed: {label}")
    if require_files:
        for split, spec in config["upstream"]["files"].items():
            path = Path(str(spec["path"]))
            require(path.is_file(), f"missing {split} parquet: {path}")
            require(path.stat().st_size == int(spec["bytes"]), f"{split} byte size changed")
            require(sha256_file(path) == spec["sha256"], f"{split} parquet hash changed")


def audit(config: Mapping[str, Any]) -> dict[str, Any]:
    denylist = load_json(Path(config["bindings"]["evaluation_denylist"]["path"]))
    required = set(config["schema"]["required_columns"])
    read_columns = list(config["schema"]["read_columns"])
    post_reference = datetime.fromisoformat(config["reporting"]["post_release_reference_date"])
    candidates: list[dict[str, Any]] = []
    seen_identity: set[str] = set()
    seen_pair: set[tuple[str, str, str]] = set()
    rejections: Counter[str] = Counter()
    native: dict[str, Any] = {}
    native_repositories: dict[str, set[str]] = {}

    import pyarrow.parquet as pq

    for native_split, spec in config["upstream"]["files"].items():
        path = Path(str(spec["path"]))
        parquet = pq.ParquetFile(path)
        require(required <= set(parquet.schema_arrow.names), f"{native_split} schema columns missing")
        require(parquet.metadata.num_rows == int(spec["published_rows"]), f"{native_split} row count changed")
        cpp_seen = 0
        accepted = 0
        repos: set[str] = set()
        post_count = 0
        for row in iter_parquet_rows(path, read_columns):
            if row.get("language") == config["schema"]["language_value"]:
                cpp_seen += 1
            candidate, reason = project_record(row, config, denylist)
            if reason == "language_mismatch":
                continue
            if reason is not None:
                rejections[reason] += 1
                continue
            assert candidate is not None
            pair = (str(candidate["repository"]), str(candidate["before"]), str(candidate["after"]))
            if str(candidate["stable_id"]) in seen_identity or pair in seen_pair:
                rejections["duplicate_identity_or_commit_pair"] += 1
                continue
            seen_identity.add(str(candidate["stable_id"]))
            seen_pair.add(pair)
            accepted += 1
            repos.add(str(candidate["repository"]))
            if candidate["commit_time"] >= post_reference:
                post_count += 1
            candidates.append(candidate)
        require(cpp_seen == int(spec["published_cpp_rows"]), f"{native_split} published C++ count changed")
        native[native_split] = {
            "all_rows": int(spec["published_rows"]),
            "cpp_rows": cpp_seen,
            "accepted_cpp_metadata": accepted,
            "repositories": len(repos),
            "post_reference_date": post_count,
        }
        native_repositories[native_split] = repos

    cap_report = cap_and_gate(candidates, config)
    identity_set = hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(seen_identity)).encode("utf-8")
    ).hexdigest()
    return {
        "version": VERSION,
        "status": "metadata_only",
        "native_split": native,
        "native_repository_overlap": len(native_repositories["train"] & native_repositories["test"]),
        "accepted_cpp_metadata_total": len(candidates),
        "accepted_repository_total": len({str(row["repository"]) for row in candidates}),
        "reject_counts": dict(sorted(rejections.items())),
        "candidate_identity_set_sha256_lf": "sha256:" + identity_set,
        "repository_resplit_gate": cap_report,
        "decision": {
            "historical_license_pilot_authorized": cap_report["all_passed"],
            "content_download_authorized": False,
            "repository_checkout_authorized": False,
            "training_authorized": False,
            "gpu_authorized": False,
            "next_action": (
                "freeze a bounded historical repository-license pilot"
                if cap_report["all_passed"]
                else "close BeetleBox without content acquisition"
            ),
        },
        "interpretation_boundary": [
            "Native train/test splits are audited as metadata only and are not reused as training splits.",
            "Issue titles and bodies were not read.",
            "No source, patch, tests, repository checkout, evaluation gold, training, GPU, or DPO was used.",
            "Commit dates after the reference date are descriptive and do not prove absence from base pretraining.",
            "A pass authorizes only a separate historical-license pilot.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/data/data_v2_beetlebox_metadata_audit_v1.json"))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)
    verify_config(config, require_files=not args.preflight_only)
    if args.preflight_only:
        print(json.dumps({"version": VERSION, "preflight": "passed"}, sort_keys=True))
        return

    output = Path(config["output_directory"])
    require(not output.exists(), f"output already exists: {output}")
    summary = audit(config)
    output.mkdir(parents=True)
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": os.environ.get("PATCHALIGN_GIT_COMMIT", "unknown"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", "local"),
        "config_sha256": sha256_file(args.config),
        "input_sha256": {
            split: spec["sha256"] for split, spec in config["upstream"]["files"].items()
        },
        "summary_sha256": sha256_file(summary_path),
        "candidate_identity_set_sha256_lf": summary["candidate_identity_set_sha256_lf"],
    }
    (output / "run-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
