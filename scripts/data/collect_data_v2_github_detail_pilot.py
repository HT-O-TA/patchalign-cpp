#!/usr/bin/env python3
"""Collect the fixed, checkpointed GitHub detail pilot without patch/source content."""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable
import urllib.error
import urllib.request

from scripts.data.check_data_v2_contract import canonical_repository, validate_contract
from scripts.data.check_data_v2_evaluation_denylist import repository_denial_reason
from scripts.data.collect_data_v2_github_metadata import has_bug_label, linked_issue_numbers


VERSION = "data-v2-github-detail-pilot-v1"
DEFAULT_CONFIG = Path("configs/data/data_v2_github_detail_pilot_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_hash(*values: object) -> str:
    payload = "\0".join(str(value) for value in values).encode("utf-8")
    return sha256_bytes(payload)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def verify_bound_file(spec: dict[str, Any], label: str) -> dict[str, Any]:
    path = Path(spec["path"])
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return load_json(path) if path.suffix == ".json" else {}


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    require(config.get("version") == VERSION, "unexpected detail pilot version")
    contract = verify_bound_file(config["contract"], "Data-v2 contract")
    validate_contract(contract)
    verify_bound_file(config["decision"], "ADR-0017")
    denylist = verify_bound_file(config["evaluation_denylist"], "evaluation denylist")
    require(denylist["scope"]["complete_for_candidate_content_acquisition"] is True, "denylist incomplete")
    discovery = config["discovery"]
    require(discovery["version"] == "data-v2-repository-pr-discovery-v2.1", "discovery version changed")
    require(discovery["git_commit"] == "3dbdbb0c0e0ecd5b94ed476a506a713248d3db9c", "discovery commit changed")
    require(discovery["slurm_job_id"] == 96939, "discovery job changed")
    require(discovery["candidates"]["count"] == 7721, "discovery candidate count changed")
    require(
        discovery["expected_capacity"]
        == {
            "train": {
                "unique_repositories_with_candidates": 143,
                "candidate_pr_upper_bound": 6565,
                "projected_sample_upper_bound_after_caps": 4078,
            },
            "validation": {
                "unique_repositories_with_candidates": 29,
                "candidate_pr_upper_bound": 1156,
                "projected_sample_upper_bound_after_caps": 440,
            },
        },
        "discovery capacity changed",
    )
    require(
        config["scope"]
        == {
            "metadata_detail_only": True,
            "patch_or_source_requested": False,
            "raw_response_stored": False,
            "text_or_user_identity_stored": False,
            "training_admitted": False,
            "gpu_authorized": False,
            "dpo_authorized": False,
        },
        "scope changed",
    )
    sampling = config["sampling"]
    require(sampling["targets"] == {"train": 160, "validation": 40}, "fixed denominator changed")
    require(sampling["minimum_repository_coverage"] == {"train": 100, "validation": 20}, "coverage gate changed")
    require(sampling["maximum_candidates_per_repository"] == 2, "repository sample cap changed")
    require(sampling["order"] == "repository_round_robin_then_sha256_seed_nul_candidate_id", "sampling order changed")
    api = config["api"]
    require(api["base_url"] == "https://api.github.com", "API base changed")
    require(api["maximum_attempts"] == 3, "retry bound changed")
    require(api["maximum_logical_requests"] == 600, "logical request budget changed")
    require(api["maximum_network_attempts_per_run"] == 606, "network attempt budget changed")
    require(api["unauthenticated_minimum_interval_seconds"] >= 61.0, "unauthenticated throttle weakened")
    require(api["authenticated_minimum_interval_seconds"] >= 0.5, "authenticated throttle weakened")
    require(sum(sampling["targets"].values()) * 3 == api["maximum_logical_requests"], "request budget inconsistent")
    gates = config["detail_gates"]
    require(gates["changed_files"] == {"minimum": 1, "maximum": 10}, "file gate changed")
    require(gates["changed_lines"] == {"minimum": 2, "maximum": 200}, "line gate changed")
    require(gates["maximum_linked_issues_checked"] == 1, "issue request cap changed")
    require(gates["require_same_repository_explicit_closing_issue"] is True, "explicit issue gate disabled")
    require(gates["require_primary_language_cpp"] is True, "language gate disabled")
    require(gates["require_nonfork_nonarchived"] is True, "repository integrity gate disabled")
    require(gates["require_merged_and_three_commit_identities"] is True, "commit identity gate disabled")
    require(gates["require_bug_label"] is True, "bug label gate disabled")
    require(gates["linked_issue_bug_label_tokens"] == ["bug", "bugs", "bugfix", "defect", "defects"], "bug label tokens changed")
    require(
        gates["allowed_spdx"]
        == ["Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "BSL-1.0", "ISC", "MIT", "Zlib"],
        "license allowlist changed",
    )
    require(gates["require_current_license_content_sha256"] is True, "license hash gate disabled")
    outcome = config["outcome_gate"]
    require(outcome == {"minimum_records": 50, "minimum_split_records": {"train": 40, "validation": 10}, "minimum_split_repositories": {"train": 30, "validation": 8}}, "outcome gate changed")
    require(config["output_directory"] == "artifacts/data-v2/github-detail-pilot-v1", "output path changed")
    return denylist


def load_discovery(config: dict[str, Any]) -> list[dict[str, Any]]:
    discovery = config["discovery"]
    candidates = verify_bound_file(discovery["candidates"], "v2.1 candidates")
    summary = verify_bound_file(discovery["summary"], "v2.1 summary")
    manifest = verify_bound_file(discovery["run_manifest"], "v2.1 run manifest")
    require(candidates == {}, "candidates must be JSONL")
    require(summary["version"] == "data-v2-repository-pr-discovery-v2.1", "discovery summary version changed")
    require(summary["github_detail_pilot_capacity_gate_passed"] is True, "capacity gate did not pass")
    require(manifest["version"] == summary["version"], "discovery manifest version mismatch")
    require(manifest["git_commit"] == discovery["git_commit"], "discovery manifest commit changed")
    require(str(manifest["slurm_job_id"]) == str(discovery["slurm_job_id"]), "discovery job changed")
    require(summary["split_stats"] == discovery["expected_capacity"], "discovery capacity artifact changed")
    require(manifest["outputs"]["candidates.jsonl"]["sha256"] == discovery["candidates"]["sha256"], "candidate reverse binding changed")
    require(manifest["outputs"]["summary.json"]["sha256"] == discovery["summary"]["sha256"], "summary reverse binding changed")
    rows = read_jsonl(Path(discovery["candidates"]["path"]))
    require(len(rows) == discovery["candidates"]["count"], "candidate count changed")
    return rows


def select_fixed_candidates(
    candidates: list[dict[str, Any]], config: dict[str, Any], denylist: dict[str, Any]
) -> list[dict[str, Any]]:
    seed = config["sampling"]["seed"]
    maximum = config["sampling"]["maximum_candidates_per_repository"]
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {"train": defaultdict(list), "validation": defaultdict(list)}
    seen: set[str] = set()
    for row in candidates:
        split = row.get("projected_split")
        require(split in grouped, "candidate split changed")
        candidate_id = str(row.get("candidate_id") or "")
        require(candidate_id and candidate_id not in seen, "duplicate candidate identity")
        require(re.fullmatch(r"ghpr-[0-9a-f]{24}", candidate_id) is not None, "invalid candidate identity")
        seen.add(candidate_id)
        repository = canonical_repository(str(row["repository_split_group"]))
        require(repository_denial_reason(repository, denylist) is None, "denied repository entered discovery")
        require(row.get("source_dataset") == "github-linked-pr-discovery-v2.1", "candidate source changed")
        copied = dict(row)
        copied["repository_split_group"] = repository
        grouped[split][repository].append(copied)

    selected: list[dict[str, Any]] = []
    coverage: dict[str, int] = {}
    for split in ("train", "validation"):
        target = config["sampling"]["targets"][split]
        repositories = sorted(grouped[split], key=lambda value: (stable_hash(seed, value), value))
        chosen: list[dict[str, Any]] = []
        for round_index in range(maximum):
            for repository in repositories:
                ranked = sorted(
                    grouped[split][repository],
                    key=lambda row: (stable_hash(seed, row["candidate_id"]), row["candidate_id"]),
                )
                if round_index < len(ranked):
                    chosen.append(ranked[round_index])
                if len(chosen) == target:
                    break
            if len(chosen) == target:
                break
        require(len(chosen) == target, f"insufficient fixed {split} candidates")
        coverage[split] = len({row["repository_split_group"] for row in chosen})
        require(coverage[split] >= config["sampling"]["minimum_repository_coverage"][split], f"insufficient {split} repository coverage")
        for row in chosen:
            row["detail_pilot_order"] = len(selected)
            selected.append(row)
    require(len(selected) == 200, "detail pilot denominator changed")
    return selected


def project_pr_detail(
    candidate: dict[str, Any], detail: dict[str, Any], config: dict[str, Any], denylist: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    number = int(detail.get("number") or 0)
    if number != int(candidate["pr_number"]):
        return None, "pr_number_mismatch"
    repo = detail.get("base", {}).get("repo") or {}
    full_name = str(repo.get("full_name") or "")
    if not re.fullmatch(r"[^/]+/[^/]+", full_name):
        return None, "missing_repository"
    canonical = canonical_repository("github.com/" + full_name)
    if canonical != candidate["repository_split_group"]:
        return None, "repository_identity_mismatch"
    denial = repository_denial_reason(canonical, denylist, is_fork=bool(repo.get("fork")))
    if denial:
        return None, denial
    if repo.get("fork"):
        return None, "fork"
    if repo.get("archived"):
        return None, "archived"
    if repo.get("language") != "C++":
        return None, "primary_language_not_cpp"
    if not detail.get("merged_at"):
        return None, "not_merged"
    shas = {
        "base_sha": str(detail.get("base", {}).get("sha") or ""),
        "head_sha": str(detail.get("head", {}).get("sha") or ""),
        "merge_commit_sha": str(detail.get("merge_commit_sha") or ""),
    }
    if any(re.fullmatch(r"[0-9a-fA-F]{40}", value) is None for value in shas.values()):
        return None, "invalid_commit_identity"
    changed_files = int(detail.get("changed_files") or 0)
    changed_lines = int(detail.get("additions") or 0) + int(detail.get("deletions") or 0)
    file_gate = config["detail_gates"]["changed_files"]
    line_gate = config["detail_gates"]["changed_lines"]
    if not file_gate["minimum"] <= changed_files <= file_gate["maximum"]:
        return None, "changed_files_out_of_range"
    if not line_gate["minimum"] <= changed_lines <= line_gate["maximum"]:
        return None, "changed_lines_out_of_range"
    issues = linked_issue_numbers(detail.get("body"), full_name)
    if not issues:
        return None, "no_explicit_same_repository_closing_issue"
    projection = {
        "repository_full_name": full_name,
        "repository_split_group": canonical,
        "pr_number": number,
        "created_at": detail.get("created_at"),
        "merged_at": detail.get("merged_at"),
        **{key: value.lower() for key, value in shas.items()},
        "changed_files": changed_files,
        "additions": int(detail.get("additions") or 0),
        "deletions": int(detail.get("deletions") or 0),
        "linked_issue_number": issues[0],
    }
    return projection, "selected"


def project_issue(number: int, document: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if document.get("pull_request"):
        return None, "linked_reference_is_pull_request"
    if int(document.get("number") or 0) != number:
        return None, "linked_issue_identity_mismatch"
    if document.get("state") != "closed":
        return None, "linked_issue_not_closed"
    if config["detail_gates"]["require_bug_label"] and not has_bug_label(document, {"pilot": config["detail_gates"]}):
        return None, "linked_issue_without_bug_label"
    return {"number": number, "state": "closed", "bug_label_matched": True}, "selected"


def project_license(document: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    license_meta = document.get("license") or {}
    spdx = str(license_meta.get("spdx_id") or "")
    if spdx not in set(config["detail_gates"]["allowed_spdx"]):
        return None, "license_not_allowlisted"
    encoded = "".join(str(document.get("content") or "").split())
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except ValueError:
        return None, "license_content_invalid"
    if not decoded:
        return None, "license_content_empty"
    return {
        "spdx_id": spdx,
        "key": license_meta.get("key"),
        "path": document.get("path"),
        "content_sha256": sha256_bytes(decoded),
    }, "selected"


class GitHubClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        token = os.environ.get(config["token_environment_variable"], "").strip()
        self.authenticated = bool(token)
        self.interval = config["authenticated_minimum_interval_seconds"] if token else config["unauthenticated_minimum_interval_seconds"]
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": config["user_agent"],
            "X-GitHub-Api-Version": config["version"],
        }
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.last_request: float | None = None
        self.actual_requests = 0

    def get(self, url_or_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
        url = url_or_path if url_or_path.startswith("https://") else self.config["base_url"] + url_or_path
        require(url.startswith(self.config["base_url"] + "/"), "refusing non-GitHub URL")
        for attempt in range(self.config["maximum_attempts"]):
            if self.last_request is not None:
                delay = self.interval - (time.monotonic() - self.last_request)
                if delay > 0:
                    time.sleep(delay)
            self.last_request = time.monotonic()
            require(
                self.actual_requests < self.config["maximum_network_attempts_per_run"],
                "network attempt budget exhausted",
            )
            self.actual_requests += 1
            try:
                request = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(request, timeout=self.config["timeout_seconds"]) as response:
                    raw = response.read()
                    return json.loads(raw), {
                        "url": url,
                        "sha256": sha256_bytes(raw),
                        "http_status": response.status,
                        "rate_limit": {key: response.headers.get(key, "") for key in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-RateLimit-Resource")},
                    }
            except urllib.error.HTTPError as error:
                if error.code in {404, 410}:
                    raw = error.read()
                    return {}, {
                        "url": url,
                        "sha256": sha256_bytes(raw),
                        "http_status": error.code,
                        "rate_limit": {key: error.headers.get(key, "") for key in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-RateLimit-Resource")},
                    }
                if error.code not in {429, 500, 502, 503, 504} or attempt + 1 == self.config["maximum_attempts"]:
                    raise RuntimeError(f"GitHub API HTTP {error.code}: {url}") from error
            except urllib.error.URLError as error:
                if attempt + 1 == self.config["maximum_attempts"]:
                    raise RuntimeError(f"GitHub API unavailable: {url}") from error
            time.sleep(2**attempt)
        raise AssertionError("unreachable")


def current_commit() -> str:
    value = os.environ.get("PATCHALIGN_GIT_COMMIT", "").strip() or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "invalid Git commit")
    return value


def checkpointed_request(
    path: Path,
    *,
    common: dict[str, Any],
    url: str,
    client: GitHubClient,
    projector: Callable[[dict[str, Any]], tuple[dict[str, Any] | None, str]],
) -> tuple[dict[str, Any], bool]:
    if path.exists():
        checkpoint = load_json(path)
        for key, value in common.items():
            require(checkpoint.get(key) == value, f"checkpoint drift: {path}: {key}")
        require(checkpoint["request_url"].casefold() == url.casefold(), f"checkpoint URL drift: {path}")
        return checkpoint, True
    document, response = client.get(url)
    status = int(response.get("http_status") or 0)
    if status in {404, 410}:
        projection, reason = None, f"http_{status}"
    else:
        require(status == 200, f"unexpected GitHub API status: {status}")
        projection, reason = projector(document)
    checkpoint = {
        **common,
        "request_url": url,
        "response": response,
        "accepted": projection is not None,
        "reason": reason,
        "projection": projection,
    }
    write_json_atomic(path, checkpoint)
    return checkpoint, False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate frozen inputs and deterministic selection without network or output writes",
    )
    args = parser.parse_args()
    config = load_json(args.config)
    denylist = validate_config(config)
    candidates = load_discovery(config)
    selected = select_fixed_candidates(candidates, config, denylist)
    config_hash = sha256_file(args.config)
    script_hash = sha256_file(Path(__file__))
    commit = current_commit()
    selected_bytes = jsonl_bytes(selected)
    selection_hash = sha256_bytes(selected_bytes)
    if args.preflight_only:
        split_counts = Counter(row["projected_split"] for row in selected)
        split_repositories = {
            split: len({row["repository_split_group"] for row in selected if row["projected_split"] == split})
            for split in ("train", "validation")
        }
        print(
            json.dumps(
                {
                    "version": VERSION,
                    "mode": "preflight-only",
                    "git_commit": commit,
                    "config_sha256": config_hash,
                    "script_sha256": script_hash,
                    "selection_sha256": selection_hash,
                    "selected_split_counts": dict(sorted(split_counts.items())),
                    "selected_split_repositories": split_repositories,
                    "network_requests": 0,
                    "output_writes": 0,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    output = Path(config["output_directory"])
    final_names = ("qualified-metadata.jsonl", "summary.json", "run-manifest.json")
    require(not any((output / name).exists() for name in final_names), "refusing to overwrite final detail outputs")
    output.mkdir(parents=True, exist_ok=True)
    selected_path = output / "selected-candidates.jsonl"
    if selected_path.exists():
        require(selected_path.read_bytes() == selected_bytes, "selected candidate drift")
    else:
        write_bytes_atomic(selected_path, selected_bytes)
    client = GitHubClient(config["api"])
    common_base = {
        "version": VERSION,
        "config_sha256": config_hash,
        "script_sha256": script_hash,
        "git_commit": commit,
        "selection_sha256": selection_hash,
    }
    rejections: Counter[str] = Counter()
    qualified: list[dict[str, Any]] = []
    cached_requests = 0
    for index, candidate in enumerate(selected, start=1):
        candidate_id = candidate["candidate_id"]
        common = {**common_base, "candidate_id": candidate_id}
        pr, cached = checkpointed_request(
            output / "checkpoints" / "pull" / f"{candidate_id}.json",
            common={**common, "stage": "pull"},
            url=candidate["pr_api_url"],
            client=client,
            projector=lambda document, row=candidate: project_pr_detail(row, document, config, denylist),
        )
        cached_requests += int(cached)
        if not pr["accepted"]:
            rejections["pull:" + pr["reason"]] += 1
            print(json.dumps({"candidate": index, "total": len(selected), "stage": "pull", "reason": pr["reason"], "cached": cached}, sort_keys=True), flush=True)
            continue
        detail = pr["projection"]
        full_name = detail["repository_full_name"]
        issue_number = detail["linked_issue_number"]
        issue, cached = checkpointed_request(
            output / "checkpoints" / "issue" / f"{candidate_id}.json",
            common={**common, "stage": "issue"},
            url=f"/repos/{full_name}/issues/{issue_number}",
            client=client,
            projector=lambda document, number=issue_number: project_issue(number, document, config),
        )
        cached_requests += int(cached)
        if not issue["accepted"]:
            rejections["issue:" + issue["reason"]] += 1
            print(json.dumps({"candidate": index, "total": len(selected), "stage": "issue", "reason": issue["reason"], "cached": cached}, sort_keys=True), flush=True)
            continue
        repository_id = hashlib.sha256(detail["repository_split_group"].encode("utf-8")).hexdigest()[:24]
        license_checkpoint = output / "checkpoints" / "license" / f"ghrepo-{repository_id}.json"
        license_common = {**common_base, "repository_split_group": detail["repository_split_group"], "stage": "license"}
        license_result, cached = checkpointed_request(
            license_checkpoint,
            common=license_common,
            url=f"/repos/{full_name}/license",
            client=client,
            projector=lambda document: project_license(document, config),
        )
        cached_requests += int(cached)
        if not license_result["accepted"]:
            rejections["license:" + license_result["reason"]] += 1
            print(json.dumps({"candidate": index, "total": len(selected), "stage": "license", "reason": license_result["reason"], "cached": cached}, sort_keys=True), flush=True)
            continue
        qualified.append(
            {
                "pilot_id": "ghdetail-" + hashlib.sha256(f'{candidate_id}\0{detail["merge_commit_sha"]}'.encode("utf-8")).hexdigest()[:24],
                "candidate_id": candidate_id,
                "source_dataset": "github-issue-linked-cpp-detail-v1",
                "projected_split": candidate["projected_split"],
                "repository_split_group": detail["repository_split_group"],
                "pr": detail,
                "linked_issue": issue["projection"],
                "license": license_result["projection"],
                "response_sha256": {
                    "pull": pr["response"]["sha256"],
                    "issue": issue["response"]["sha256"],
                    "license": license_result["response"]["sha256"],
                },
                "content_boundaries": {"patch_or_source_stored": False, "raw_response_stored": False, "text_or_user_identity_stored": False},
                "training_admitted": False,
            }
        )
        print(json.dumps({"candidate": index, "total": len(selected), "qualified": len(qualified), "cached": cached}, sort_keys=True), flush=True)

    split_counts = Counter(row["projected_split"] for row in qualified)
    split_repositories = {
        split: len({row["repository_split_group"] for row in qualified if row["projected_split"] == split})
        for split in ("train", "validation")
    }
    gate = config["outcome_gate"]
    checks = {
        "minimum_records": len(qualified) >= gate["minimum_records"],
        **{f"{split}_minimum_records": split_counts[split] >= gate["minimum_split_records"][split] for split in ("train", "validation")},
        **{f"{split}_minimum_repositories": split_repositories[split] >= gate["minimum_split_repositories"][split] for split in ("train", "validation")},
    }
    summary = {
        "version": VERSION,
        "fixed_denominator": len(selected),
        "qualified_records": len(qualified),
        "qualified_split_counts": dict(sorted(split_counts.items())),
        "qualified_split_repositories": split_repositories,
        "rejections": dict(sorted(rejections.items())),
        "outcome_checks": checks,
        "execution_content_pilot_authorized": all(checks.values()),
        "patch_or_source_stored": False,
        "training_admitted": False,
        "gpu_used": False,
    }
    qualified_path = output / "qualified-metadata.jsonl"
    summary_path = output / "summary.json"
    write_bytes_atomic(qualified_path, jsonl_bytes(qualified))
    write_json_atomic(summary_path, summary)
    manifest = {
        "version": VERSION,
        "git_commit": commit,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": config_hash,
        "script_sha256": script_hash,
        "discovery_run_manifest_sha256": config["discovery"]["run_manifest"]["sha256"],
        "selection_sha256": selection_hash,
        "authenticated_github_api": client.authenticated,
        "network_requests": client.actual_requests,
        "cached_requests": cached_requests,
        "content_boundaries": config["scope"],
        "outputs": {
            "selected-candidates.jsonl": {"count": len(selected), "sha256": sha256_file(selected_path)},
            "qualified-metadata.jsonl": {"count": len(qualified), "sha256": sha256_file(qualified_path)},
            "summary.json": {"sha256": sha256_file(summary_path)},
        },
    }
    write_json_atomic(output / "run-manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
