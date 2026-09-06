#!/usr/bin/env python3
"""Collect a projected GitHub C++ repair metadata pilot without patch content."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import time
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.data.check_data_v2_contract import canonical_repository, validate_contract


VERSION = "data-v2-github-metadata-pilot-v1.1"
ISSUE_PATTERN = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:(?P<repository>[\w.-]+/[\w.-]+))?#(?P<number>\d+)\b",
    re.IGNORECASE,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_id(*values: object) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "ghmeta-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def linked_issue_numbers(body: str | None, repository_full_name: str | None = None) -> list[int]:
    numbers: set[int] = set()
    for match in ISSUE_PATTERN.finditer(body or ""):
        referenced_repository = (match.group("repository") or "").lower()
        if referenced_repository and repository_full_name and referenced_repository != repository_full_name.lower():
            continue
        numbers.add(int(match.group("number")))
    return sorted(numbers)


def has_bug_label(issue_document: dict[str, Any], config: dict[str, Any]) -> bool:
    allowed = set(config["pilot"]["linked_issue_bug_label_tokens"])
    for label in issue_document.get("labels", []):
        name = str(label.get("name") or "").lower()
        if allowed.intersection(re.findall(r"[a-z0-9]+", name)):
            return True
    return False


def is_denied_repository(canonical: str, config: dict[str, Any]) -> bool:
    denied = config["denylist"]
    if canonical in set(denied["exact_canonical_repositories"]):
        return True
    repo_name = canonical.rsplit("/", 1)[-1]
    return repo_name in set(denied["exact_repository_name_aliases"])


def verify_bound_file(spec: dict[str, str], label: str) -> dict[str, Any]:
    path = Path(spec["path"])
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else {}


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected metadata pilot version")
    contract = verify_bound_file(config["contract"], "Data-v2.1 contract")
    validate_contract(contract)
    verify_bound_file(config["decision"], "ADR-0010")
    api = config["api"]
    require(api["base_url"] == "https://api.github.com", "unexpected API base")
    require(api["timeout_seconds"] == 30, "API timeout changed")
    require(api["maximum_attempts"] == 3, "retry policy changed")
    require(api["unauthenticated_core_request_budget"] == 60, "unauthenticated API budget changed")
    search = config["search"]
    require(search["per_page"] == 100 and search["page"] == 1, "search page changed")
    require("is:pr" in search["query"] and "is:merged" in search["query"], "search no longer selects merged PRs")
    pilot = config["pilot"]
    require(pilot["target_unique_repositories"] == 15, "pilot repository target changed")
    require(pilot["maximum_candidate_details"] == 18, "candidate detail request cap changed")
    maximum_core_requests = pilot["maximum_candidate_details"] * 3
    require(api["planned_maximum_core_requests"] == maximum_core_requests, "planned API request bound changed")
    require(maximum_core_requests <= api["unauthenticated_core_request_budget"], "pilot can exceed unauthenticated core API budget")
    require(pilot["maximum_records_per_repository"] == 1, "per-repository pilot cap changed")
    require(pilot["require_explicit_linked_issue"] is True, "issue-link requirement disabled")
    require(pilot["require_linked_issue_in_same_repository"] is True, "same-repository issue requirement disabled")
    require(pilot["maximum_linked_issues_checked_per_candidate"] == 1, "linked-issue request cap changed")
    require(pilot["require_linked_issue_bug_label"] is True, "linked-issue bug-label requirement disabled")
    require("label:bug" not in search["query"], "PR-label query regression reintroduced")
    projection = config["projection"]
    for key in ("store_patch", "store_source_code", "store_title_or_body", "store_user_identity", "store_license_text", "store_linked_issue_title_or_body"):
        require(projection[key] is False, f"forbidden projection enabled: {key}")
    require(projection["store_title_and_body_sha256"] is True, "text hash projection disabled")
    require(config["denylist"]["complete_for_patch_content_admission"] is False, "pilot denylist falsely marked content-complete")


class GitHubClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.base = config["base_url"].rstrip("/")
        token = os.environ.get(config["token_environment_variable"], "").strip()
        self.authenticated = bool(token)
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": config["user_agent"],
            "X-GitHub-Api-Version": config["version"],
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.response_hashes: list[dict[str, Any]] = []
        self.last_rate: dict[str, str] = {}

    def get(self, url_or_path: str) -> dict[str, Any]:
        url = url_or_path if url_or_path.startswith("https://") else self.base + url_or_path
        require(url.startswith(self.base + "/"), f"refusing non-GitHub API URL: {url}")
        attempts = self.config["maximum_attempts"]
        for attempt in range(attempts):
            request = urllib.request.Request(url, headers=self.headers)
            try:
                with urllib.request.urlopen(request, timeout=self.config["timeout_seconds"]) as response:
                    raw = response.read()
                    self.last_rate = {
                        key: response.headers.get(key, "")
                        for key in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-RateLimit-Resource")
                    }
                    self.response_hashes.append({"url": url, "sha256": sha256_bytes(raw), "etag": response.headers.get("ETag", "")})
                    return json.loads(raw)
            except urllib.error.HTTPError as error:
                retryable = error.code in {429, 500, 502, 503, 504}
                if not retryable or attempt + 1 == attempts:
                    raise RuntimeError(f"GitHub API HTTP {error.code}: {url}") from error
            except urllib.error.URLError as error:
                if attempt + 1 == attempts:
                    raise RuntimeError(f"GitHub API unavailable: {url}: {error.reason}") from error
            time.sleep(2**attempt)
        raise AssertionError("unreachable")


def evaluate_candidate(
    detail: dict[str, Any],
    linked_issue_document: dict[str, Any] | None,
    license_document: dict[str, Any] | None,
    config: dict[str, Any],
    response_hashes: dict[str, str],
) -> tuple[dict[str, Any] | None, str]:
    repo = detail.get("base", {}).get("repo") or {}
    full_name = str(repo.get("full_name") or "")
    if not full_name:
        return None, "missing_repository"
    canonical = canonical_repository("github.com/" + full_name)
    if is_denied_repository(canonical, config):
        return None, "reserved_benchmark_repository"
    pilot = config["pilot"]
    if repo.get("fork"):
        return None, "fork"
    if repo.get("archived"):
        return None, "archived"
    if pilot["require_primary_language_cpp"] and repo.get("language") != "C++":
        return None, "primary_language_not_cpp"
    if int(repo.get("stargazers_count") or 0) < pilot["minimum_repository_stars"]:
        return None, "insufficient_stars"
    if not detail.get("merged_at") or not detail.get("merge_commit_sha"):
        return None, "not_merged"
    changed_files = int(detail.get("changed_files") or 0)
    changed_lines = int(detail.get("additions") or 0) + int(detail.get("deletions") or 0)
    if changed_files < 1 or changed_files > pilot["maximum_changed_files"]:
        return None, "changed_files_out_of_range"
    if not pilot["minimum_changed_lines"] <= changed_lines <= pilot["maximum_changed_lines"]:
        return None, "changed_lines_out_of_range"
    issues = linked_issue_numbers(detail.get("body"), full_name)
    if pilot["require_explicit_linked_issue"] and not issues:
        return None, "no_explicit_same_repository_linked_issue"
    if not linked_issue_document:
        return None, "linked_issue_metadata_unavailable"
    if linked_issue_document.get("pull_request"):
        return None, "linked_reference_is_pull_request"
    if int(linked_issue_document.get("number") or 0) not in issues:
        return None, "linked_issue_identity_mismatch"
    if pilot["require_linked_issue_bug_label"] and not has_bug_label(linked_issue_document, config):
        return None, "linked_issue_without_bug_label"
    if not license_document:
        return None, "license_document_unavailable"
    license_meta = license_document.get("license") or {}
    spdx = license_meta.get("spdx_id")
    if spdx not in set(pilot["allowed_spdx"]):
        return None, "license_not_allowlisted"
    encoded = "".join(str(license_document.get("content") or "").split())
    try:
        license_bytes = base64.b64decode(encoded, validate=True)
    except ValueError:
        return None, "license_content_invalid"
    if pilot["require_current_license_content_sha256"] and not license_bytes:
        return None, "license_content_empty"

    title = str(detail.get("title") or "")
    body = str(detail.get("body") or "")
    number = int(detail["number"])
    record = {
        "pilot_id": stable_id(canonical, number, detail["merge_commit_sha"]),
        "source_dataset": "GitHub-issue-linked-C++-metadata",
        "repository_split_group": canonical,
        "repository_full_name": full_name,
        "repository_url": repo.get("html_url"),
        "repository_primary_language": repo.get("language"),
        "repository_stars_at_collection": int(repo.get("stargazers_count") or 0),
        "pr_number": number,
        "pr_url": detail.get("html_url"),
        "created_at": detail.get("created_at"),
        "merged_at": detail.get("merged_at"),
        "base_sha": detail.get("base", {}).get("sha"),
        "head_sha": detail.get("head", {}).get("sha"),
        "fix_commit_sha_candidate": detail.get("merge_commit_sha"),
        "parent_commit_sha_verified": False,
        "changed_files": changed_files,
        "additions": int(detail.get("additions") or 0),
        "deletions": int(detail.get("deletions") or 0),
        "explicit_linked_issue_numbers": issues,
        "linked_issue": {
            "number": int(linked_issue_document["number"]),
            "html_url": linked_issue_document.get("html_url"),
            "state": linked_issue_document.get("state"),
            "labels": sorted(str(item.get("name")) for item in linked_issue_document.get("labels", []) if item.get("name")),
            "title_sha256": sha256_text(str(linked_issue_document.get("title") or "")),
            "body_sha256": sha256_text(str(linked_issue_document.get("body") or "")),
        },
        "pr_labels": sorted(str(item.get("name")) for item in detail.get("labels", []) if item.get("name")),
        "title_sha256": sha256_text(title),
        "body_sha256": sha256_text(body),
        "license": {
            "spdx_id": spdx,
            "key": license_meta.get("key"),
            "path": license_document.get("path"),
            "html_url": license_document.get("html_url"),
            "content_sha256": sha256_bytes(license_bytes),
        },
        "api_response_sha256": response_hashes,
        "projection": {
            "patch_stored": False,
            "source_code_stored": False,
            "title_or_body_stored": False,
            "user_identity_stored": False,
            "license_text_stored": False,
            "linked_issue_title_or_body_stored": False,
        },
        "training_admitted": False,
    }
    return record, "selected"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect(config: dict[str, Any], client: GitHubClient) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    search = config["search"]
    query = urllib.parse.urlencode({"q": search["query"], "sort": search["sort"], "order": search["order"], "per_page": search["per_page"], "page": search["page"]})
    search_response = client.get("/search/issues?" + query)
    rejects: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    selected_repositories: set[str] = set()
    target = config["pilot"]["target_unique_repositories"]
    maximum_details = config["pilot"]["maximum_candidate_details"]
    details_requested = 0
    for item in search_response.get("items", []):
        if len(selected_repositories) >= target or details_requested >= maximum_details:
            break
        pull_url = str((item.get("pull_request") or {}).get("url") or "")
        if not pull_url:
            rejects["search_item_missing_pull_url"] += 1
            continue
        detail = client.get(pull_url)
        details_requested += 1
        repo = detail.get("base", {}).get("repo") or {}
        full_name = str(repo.get("full_name") or "")
        if not full_name:
            rejects["missing_repository"] += 1
            continue
        canonical = canonical_repository("github.com/" + full_name)
        if canonical in selected_repositories:
            rejects["repository_pilot_cap"] += 1
            continue
        detail_hash = client.response_hashes[-1]["sha256"]
        response_hashes = {"pull": detail_hash, "linked_issue": "", "license": ""}
        _, reason = evaluate_candidate(detail, None, None, config, response_hashes)
        if reason != "linked_issue_metadata_unavailable":
            rejects[reason] += 1
            continue

        issue_number = linked_issue_numbers(detail.get("body"), full_name)[0]
        try:
            linked_issue_document = client.get(f"/repos/{full_name}/issues/{issue_number}")
            response_hashes["linked_issue"] = client.response_hashes[-1]["sha256"]
        except RuntimeError:
            rejects["linked_issue_metadata_unavailable"] += 1
            continue
        _, reason = evaluate_candidate(detail, linked_issue_document, None, config, response_hashes)
        if reason != "license_document_unavailable":
            rejects[reason] += 1
            continue

        try:
            license_document = client.get("/repos/" + full_name + "/license")
            response_hashes["license"] = client.response_hashes[-1]["sha256"]
        except RuntimeError:
            rejects["license_document_unavailable"] += 1
            continue
        record, reason = evaluate_candidate(detail, linked_issue_document, license_document, config, response_hashes)
        if record is None:
            rejects[reason] += 1
            continue
        records.append(record)
        selected_repositories.add(canonical)

    summary = {
        "version": VERSION,
        "query_total_count": int(search_response.get("total_count") or 0),
        "query_incomplete_results": bool(search_response.get("incomplete_results")),
        "search_items_examined": sum(rejects.values()) + len(records),
        "candidate_details_requested": details_requested,
        "candidate_detail_request_cap": maximum_details,
        "selected_records": len(records),
        "selected_unique_repositories": len(selected_repositories),
        "target_unique_repositories": target,
        "target_met": len(selected_repositories) >= target,
        "rejections": dict(sorted(rejects.items())),
        "license_spdx": dict(sorted(Counter(row["license"]["spdx_id"] for row in records).items())),
        "changed_files": {"minimum": min((row["changed_files"] for row in records), default=None), "maximum": max((row["changed_files"] for row in records), default=None)},
        "changed_lines": {"minimum": min((row["additions"] + row["deletions"] for row in records), default=None), "maximum": max((row["additions"] + row["deletions"] for row in records), default=None)},
        "patch_or_source_content_stored": False,
        "training_admitted": False,
        "gpu_used": False,
    }
    git_commit = os.environ.get("PATCHALIGN_GIT_COMMIT", "").strip()
    if not git_commit:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", git_commit) is not None, "invalid Git commit identity")
    manifest = {
        "version": VERSION,
        "git_commit": git_commit,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256_file(Path("configs/data/data_v2_metadata_pilot_v1_1.json")),
        "contract_sha256": config["contract"]["sha256"],
        "decision_sha256": config["decision"]["sha256"],
        "authenticated_api": client.authenticated,
        "api_version": config["api"]["version"],
        "search": search,
        "response_hashes": client.response_hashes,
        "final_rate_limit_headers": client.last_rate,
        "content_boundaries": {
            "patch_requested_or_stored": False,
            "source_code_requested_or_stored": False,
            "license_text_requested_for_hash_only": True,
            "linked_issue_title_or_body_requested_for_hash_only": True,
            "evaluation_gold_consumed": False,
        },
    }
    return records, summary, manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/data/data_v2_metadata_pilot_v1_1.json"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    output = Path(config["output_directory"])
    require(not output.exists(), f"output already exists: {output}")
    client = GitHubClient(config["api"])
    records, summary, manifest = collect(config, client)
    output.mkdir(parents=True)
    records_path = output / "repositories.jsonl"
    records_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    summary_path = output / "summary.json"
    write_json(summary_path, summary)
    manifest["outputs"] = {
        "repositories.jsonl": {"count": len(records), "sha256": sha256_file(records_path)},
        "summary.json": {"sha256": sha256_file(summary_path)},
    }
    write_json(output / "run-manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
