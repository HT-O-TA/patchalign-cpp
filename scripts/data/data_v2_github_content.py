"""Pure projections and Git-diff checks for the fixed GitHub content pilot."""

from __future__ import annotations

import base64
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from scripts.data.collect_data_v2_github_detail_pilot import sha256_bytes
from scripts.data.data_v2_git_diff import parse_zero_context_diff


SHA_RE = re.compile(r"[0-9a-f]{40}")


def project_commit(
    document: Mapping[str, Any], expected_sha: str, head_sha: str
) -> tuple[dict[str, Any] | None, str]:
    sha = str(document.get("sha") or "").lower()
    if sha != expected_sha:
        return None, "merge_commit_identity_mismatch"
    parents = [str(row.get("sha") or "").lower() for row in document.get("parents", [])]
    if len(parents) not in {1, 2} or any(SHA_RE.fullmatch(value) is None for value in parents):
        return None, "unsupported_merge_parent_count"
    if len(parents) == 2 and parents[1] != head_sha:
        return None, "merge_second_parent_not_head"
    return {
        "fixed_commit_sha": sha,
        "parent_commit_sha": parents[0],
        "parent_count": len(parents),
        "second_parent_sha": parents[1] if len(parents) == 2 else None,
    }, "selected"


def project_pr_commits(
    document: object, expected_head_sha: str, per_page: int
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(document, list) or not document:
        return None, "pr_commit_list_empty_or_invalid"
    if len(document) >= per_page:
        return None, "pr_commit_list_pagination_ambiguous"
    commits = [str(row.get("sha") or "").lower() for row in document if isinstance(row, Mapping)]
    if len(commits) != len(document) or any(SHA_RE.fullmatch(value) is None for value in commits):
        return None, "pr_commit_identity_invalid"
    if commits[-1] != expected_head_sha:
        return None, "last_pr_commit_not_head"
    return {
        "count": len(commits),
        "first_sha": commits[0],
        "last_sha": commits[-1],
        "ordered_commits_sha256": sha256_bytes("\n".join(commits).encode("ascii")),
    }, "selected"


def project_pr_files(
    document: object, expected_count: int, per_page: int
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(document, list) or len(document) != expected_count:
        return None, "pr_file_count_mismatch"
    if len(document) >= per_page:
        return None, "pr_file_list_pagination_ambiguous"
    files = []
    seen = set()
    for row in document:
        if not isinstance(row, Mapping):
            return None, "pr_file_entry_invalid"
        path = str(row.get("filename") or "")
        status = str(row.get("status") or "")
        if not safe_relative_path(path) or path in seen:
            return None, "pr_file_path_invalid"
        if status not in {"added", "modified", "removed"}:
            return None, "pr_file_status_unsupported"
        additions = row.get("additions")
        deletions = row.get("deletions")
        if not isinstance(additions, int) or not isinstance(deletions, int):
            return None, "pr_file_stats_invalid"
        seen.add(path)
        files.append(
            {
                "path": path,
                "status": status,
                "additions": additions,
                "deletions": deletions,
            }
        )
    return {"count": len(files), "files": sorted(files, key=lambda row: row["path"])}, "selected"


def project_license(
    document: Mapping[str, Any], allowed_spdx: set[str]
) -> tuple[dict[str, Any] | None, str]:
    license_metadata = document.get("license") or {}
    spdx = str(license_metadata.get("spdx_id") or "")
    if spdx not in allowed_spdx:
        return None, "historical_license_not_allowlisted"
    path = str(document.get("path") or "")
    if not safe_relative_path(path):
        return None, "historical_license_path_invalid"
    encoded = "".join(str(document.get("content") or "").split())
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError:
        return None, "historical_license_content_invalid"
    if not content:
        return None, "historical_license_content_empty"
    return {
        "spdx_id": spdx,
        "key": license_metadata.get("key"),
        "path": path,
        "content_sha256": sha256_bytes(content),
    }, "selected"


def safe_relative_path(value: str) -> bool:
    if not value or "\0" in value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def parse_name_status_z(payload: bytes) -> list[dict[str, str]]:
    fields = payload.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise ValueError("malformed name-status output")
    rows = []
    for index in range(0, len(fields), 2):
        status = fields[index].decode("ascii")
        path = fields[index + 1].decode("utf-8")
        if status not in {"A", "M", "D"} or not safe_relative_path(path):
            raise ValueError("unsupported name-status entry")
        rows.append({"status": status, "path": path})
    if len({row["path"] for row in rows}) != len(rows):
        raise ValueError("duplicate name-status path")
    return sorted(rows, key=lambda row: row["path"])


def parse_numstat_z(payload: bytes) -> list[dict[str, Any]]:
    fields = payload.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    rows = []
    for field in fields:
        parts = field.split(b"\t", 2)
        if len(parts) != 3 or b"-" in parts[:2]:
            raise ValueError("binary or malformed numstat entry")
        additions = int(parts[0])
        deletions = int(parts[1])
        path = parts[2].decode("utf-8")
        if additions < 0 or deletions < 0 or not safe_relative_path(path):
            raise ValueError("invalid numstat entry")
        rows.append({"path": path, "additions": additions, "deletions": deletions})
    if len({row["path"] for row in rows}) != len(rows):
        raise ValueError("duplicate numstat path")
    return sorted(rows, key=lambda row: row["path"])


def is_test_path(path: str, components: set[str]) -> bool:
    return any(part.casefold() in components for part in PurePosixPath(path).parts[:-1])


def is_build_manifest(path: str, names: set[str], suffixes: set[str]) -> bool:
    pure = PurePosixPath(path)
    return pure.name in names or pure.suffix.casefold() in suffixes


def analyze_diff(
    *,
    name_status: list[dict[str, str]],
    numstat: list[dict[str, Any]],
    pr_files: list[dict[str, Any]],
    target_diff: bytes,
    target_parent_content: bytes,
    target_fixed_content: bytes,
    config: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    status_map = {"A": "added", "M": "modified", "D": "removed"}
    if {row["path"] for row in name_status} != {row["path"] for row in numstat}:
        return None, "local_name_status_numstat_mismatch"
    local_by_path = {
        row["path"]: {
            "status": status_map[row["status"]],
            "additions": next(item["additions"] for item in numstat if item["path"] == row["path"]),
            "deletions": next(item["deletions"] for item in numstat if item["path"] == row["path"]),
        }
        for row in name_status
    }
    api_by_path = {
        row["path"]: {
            "status": row["status"],
            "additions": row["additions"],
            "deletions": row["deletions"],
        }
        for row in pr_files
    }
    if local_by_path != api_by_path:
        return None, "local_diff_does_not_match_pr_files"
    rules = config["commit_and_diff"]
    test_components = {value.casefold() for value in rules["test_path_components"]}
    production_extensions = {value.casefold() for value in rules["production_extensions"]}
    tests = [row for row in name_status if is_test_path(row["path"], test_components)]
    production = [
        row
        for row in name_status
        if not is_test_path(row["path"], test_components)
        and PurePosixPath(row["path"]).suffix.casefold() in production_extensions
    ]
    if len(production) != rules["required_production_targets"]:
        return None, "production_target_count_mismatch"
    if len(tests) < rules["minimum_test_files"]:
        return None, "test_file_missing"
    target = production[0]
    if target["status"] != "M":
        return None, "production_target_not_modified_existing"
    manifest_names = set(rules["build_manifest_names"])
    manifest_suffixes = {value.casefold() for value in rules["build_manifest_suffixes"]}
    unsafe_manifests = [
        row["path"]
        for row in name_status
        if not is_test_path(row["path"], test_components)
        and is_build_manifest(row["path"], manifest_names, manifest_suffixes)
    ]
    if unsafe_manifests:
        return None, "outside_test_build_manifest_delta"
    try:
        parent_text = target_parent_content.decode("utf-8")
        fixed_text = target_fixed_content.decode("utf-8")
    except UnicodeDecodeError:
        return None, "production_target_not_utf8"
    if "\0" in parent_text or "\0" in fixed_text:
        return None, "production_target_binary"
    try:
        parsed_diff = parse_zero_context_diff(target_diff)
    except ValueError as error:
        return None, "production_target_diff_invalid:" + str(error)
    return {
        "target_path": target["path"],
        "test_files": tests,
        "all_changed_files": name_status,
        "target_parent_sha256": sha256_bytes(target_parent_content),
        "target_fixed_sha256": sha256_bytes(target_fixed_content),
        "target_diff_sha256": sha256_bytes(target_diff),
        "target_old_ranges": [list(value) for value in parsed_diff.old_ranges],
    }, "selected"
