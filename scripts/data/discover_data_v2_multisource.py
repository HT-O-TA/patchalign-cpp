#!/usr/bin/env python3
"""Metadata-only, checkpointed Data-v2 multi-source capacity discovery."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from scripts.data.check_data_v2_contract import assign_new_split, canonical_repository, validate_contract

VERSION = "data-v2-multisource-discovery-v1"
DEFAULT_CONFIG = Path("configs/data/data_v2_multisource_discovery_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_bound_file(spec: dict[str, str], label: str) -> dict[str, Any]:
    path = Path(spec["path"])
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return load_json(path) if path.suffix == ".json" else {}


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def query_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config["github_issue_linked_cpp"]["search"]
    cursor = date.fromisoformat(search["start_date"])
    final = date.fromisoformat(search["end_date"])
    specs: list[dict[str, Any]] = []
    window = 0
    while cursor <= final:
        next_start = add_months(cursor, search["window_months"])
        window_end = min(final, date.fromordinal(next_start.toordinal() - 1))
        for order in search["orders"]:
            query = f'{search["base_query"]} merged:{cursor.isoformat()}..{window_end.isoformat()}'
            specs.append({"query_id": f"q{window:02d}-{order}", "window_start": cursor.isoformat(), "window_end": window_end.isoformat(), "query": query, "sort": search["sort"], "order": order, "per_page": search["per_page"], "page": search["page"]})
        cursor = next_start
        window += 1
    return specs


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    require(config.get("version") == VERSION, "unexpected discovery version")
    contract = verify_bound_file(config["contract"], "Data-v2 contract")
    validate_contract(contract)
    source_admission = verify_bound_file(config["source_admission"], "source admission registry")
    require(source_admission["version"] == "data-v2-source-admission-v1", "wrong source registry")
    verify_bound_file(config["decision"], "ADR-0012")
    deny_config = verify_bound_file(config["legacy_denylist"], "legacy denylist")
    require(deny_config["denylist"]["complete_for_patch_content_admission"] is False, "legacy denylist completeness unexpectedly changed")
    require(config["legacy_denylist"]["complete_for_patch_content_admission"] is False, "content denylist declared complete")
    require(config["scope"] == {"metadata_only": True, "patch_or_source_download_authorized": False, "training_dataset_freeze_authorized": False, "gpu_authorized": False, "dpo_authorized": False}, "discovery scope changed")
    github = config["github_issue_linked_cpp"]
    api = github["api"]
    require(api["base_url"] == "https://api.github.com", "unexpected GitHub API base")
    require(api["timeout_seconds"] == 30 and api["maximum_attempts"] == 3, "request retry policy changed")
    require(api["minimum_request_interval_seconds"] >= 7.0, "unauthenticated search throttle weakened")
    require(api["maximum_search_requests"] == 64, "search request budget changed")
    search = github["search"]
    require(search["base_query"] == "is:pr is:merged language:C++ archived:false stars:>=20", "base query changed")
    require((search["start_date"], search["end_date"], search["window_months"]) == ("2018-01-01", "2025-12-31", 3), "time windows changed")
    require(search["orders"] == ["asc", "desc"], "query orders changed")
    require(search["per_page"] == 100 and search["page"] == 1, "search page budget changed")
    specs = query_specs(config)
    require(len(specs) == 64 and len(specs) <= api["maximum_search_requests"], "query matrix changed or exceeds budget")
    require(config["as_of"] == "2026-09-07", "discovery date changed")
    require(config["output_directory"] == "artifacts/data-v2/multisource-discovery-v1", "output directory changed")
    require(github["role"] == "primary_repository_diversity_discovery", "GitHub source role changed")
    projection = github["projection"]
    require(projection == {"store_repository_identity": True, "store_pr_number_and_api_url": True, "store_timestamps": True, "store_title_body_labels_user": False, "store_patch_or_source": False, "store_raw_response": False, "store_response_sha256": True}, "projection contract changed")
    for forbidden in ("store_title_body_labels_user", "store_patch_or_source", "store_raw_response"):
        require(projection[forbidden] is False, f"sensitive projection enabled: {forbidden}")
    require(github["capacity_gate"] == {"train_minimum_unique_repositories": 100, "validation_minimum_unique_repositories": 20, "train_minimum_candidate_pr_upper_bound": 1000, "validation_minimum_candidate_pr_upper_bound": 100, "train_minimum_projected_sample_upper_bound_after_caps": 2000, "validation_minimum_projected_sample_upper_bound_after_caps": 200, "maximum_samples_per_candidate_family": 2, "repository_caps": {"train": 40, "validation": 20}, "all_queries_complete_required": True}, "capacity gate changed")
    multi = config["multi_swe_rl"]
    require(multi["revision"] == "9777648932daa214ba18c70c81e85821b5836f32", "Multi-SWE-RL revision changed")
    require(len(multi["cpp_repositories"]) == 9 and multi["all_cpp_repositories_reserved"] is True, "Multi-SWE-RL boundary changed")
    require(set(multi["cpp_repositories"]) <= set(deny_config["denylist"]["exact_canonical_repositories"]), "a Multi-SWE-RL C++ repository is not reserved")
    require(multi["training_content_download_authorized"] is False, "Multi-SWE-RL training download enabled")
    rbr = config["runbugrun_v2"]
    require(rbr["tag"] == "v2" and rbr["revision"] == "bbac70b7ae7331d87892e861356cf133476bc938", "RunBugRun v2 identity changed")
    require(rbr["release_asset"]["size_bytes"] == 120501798, "RunBugRun asset size changed")
    require(rbr["repository_diversity_credit"] == 0, "RunBugRun assigned repository diversity credit")
    require(rbr["release_download_requires_new_contract"] is True, "RunBugRun release gate weakened")
    require(rbr["training_admission_authorized"] is False, "RunBugRun training admission enabled")
    return deny_config


def repository_from_search_url(value: str) -> str:
    match = re.fullmatch(r"https://api\.github\.com/repos/([^/]+)/([^/]+)", value)
    require(match is not None, f"unexpected repository API URL: {value}")
    return canonical_repository(f"github.com/{match.group(1)}/{match.group(2)}")


def is_denied_repository(canonical: str, deny_config: dict[str, Any]) -> bool:
    denied = deny_config["denylist"]
    return canonical in set(denied["exact_canonical_repositories"]) or canonical.rsplit("/", 1)[-1] in set(denied["exact_repository_name_aliases"])


def project_search_item(item: dict[str, Any], query_id: str, deny_config: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    pull_url = str((item.get("pull_request") or {}).get("url") or "")
    if not pull_url.startswith("https://api.github.com/repos/"):
        return None, "missing_pull_request_api_url"
    try:
        canonical = repository_from_search_url(str(item.get("repository_url") or ""))
    except RuntimeError:
        return None, "invalid_repository_api_url"
    if is_denied_repository(canonical, deny_config):
        return None, "reserved_repository"
    number = int(item.get("number") or 0)
    if number <= 0:
        return None, "invalid_pr_number"
    candidate_id = "ghdisc-" + hashlib.sha256(f"{canonical}\0{number}".encode()).hexdigest()[:24]
    record = {"candidate_id": candidate_id, "source_dataset": "github-issue-linked-cpp-discovery", "repository_split_group": canonical, "pr_number": number, "pr_api_url": pull_url, "created_at": item.get("created_at"), "updated_at": item.get("updated_at"), "closed_at": item.get("closed_at"), "query_ids": [query_id], "sampling_family_status": "candidate_one_pr_upper_bound", "training_admitted": False}
    require(not {"title", "body", "labels", "user", "assignee", "author_association"}.intersection(record), "sensitive field entered projection")
    return record, "selected"


class GitHubSearchClient:
    def __init__(self, api: dict[str, Any]) -> None:
        self.api = api
        token = os.environ.get(api["token_environment_variable"], "").strip()
        self.authenticated = bool(token)
        self.headers = {"Accept": "application/vnd.github+json", "User-Agent": api["user_agent"], "X-GitHub-Api-Version": api["version"]}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.last_request: float | None = None

    def search(self, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        parameters = {"q": spec["query"], "sort": spec["sort"], "order": spec["order"], "per_page": spec["per_page"], "page": spec["page"]}
        url = self.api["base_url"] + "/search/issues?" + urllib.parse.urlencode(parameters)
        for attempt in range(self.api["maximum_attempts"]):
            if self.last_request is not None:
                delay = self.api["minimum_request_interval_seconds"] - (time.monotonic() - self.last_request)
                if delay > 0:
                    time.sleep(delay)
            self.last_request = time.monotonic()
            try:
                request = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(request, timeout=self.api["timeout_seconds"]) as response:
                    raw = response.read()
                    headers = {key: response.headers.get(key, "") for key in ("ETag", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-RateLimit-Resource")}
                    return json.loads(raw), {"url": url, "sha256": sha256_bytes(raw), "headers": headers}
            except urllib.error.HTTPError as error:
                if error.code not in {403, 429, 500, 502, 503, 504} or attempt + 1 == self.api["maximum_attempts"]:
                    raise RuntimeError(f"GitHub search HTTP {error.code}: {url}") from error
            except urllib.error.URLError as error:
                if attempt + 1 == self.api["maximum_attempts"]:
                    raise RuntimeError(f"GitHub search unavailable: {error.reason}") from error
            time.sleep(2**attempt)
        raise AssertionError("unreachable")


def merge_checkpoint_records(checkpoints: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    merged: dict[str, dict[str, Any]] = {}
    rejected: Counter[str] = Counter()
    for checkpoint in checkpoints:
        rejected.update(checkpoint["rejections"])
        for record in checkpoint["records"]:
            key = record["candidate_id"]
            if key not in merged:
                merged[key] = dict(record)
            else:
                merged[key]["query_ids"] = sorted(set(merged[key]["query_ids"]) | set(record["query_ids"]))
    return sorted(merged.values(), key=lambda row: (row["repository_split_group"], row["pr_number"])), rejected


def summarize_capacity(records: list[dict[str, Any]], config: dict[str, Any], queries_complete: bool) -> dict[str, Any]:
    contract = load_json(Path(config["contract"]["path"]))
    seed = contract["split"]["hash_seed"]
    validation_percent = contract["split"]["new_split_group_validation_percent"]
    by_split_repo: dict[str, dict[str, int]] = {"train": defaultdict(int), "validation": defaultdict(int)}
    for row in records:
        split = assign_new_split(row["repository_split_group"], validation_percent, seed)
        row["projected_split"] = split
        by_split_repo[split][row["repository_split_group"]] += 1
    gate = config["github_issue_linked_cpp"]["capacity_gate"]
    split_stats: dict[str, dict[str, int]] = {}
    for split in ("train", "validation"):
        counts = by_split_repo[split]
        split_stats[split] = {"unique_repositories": len(counts), "candidate_pr_upper_bound": sum(counts.values()), "projected_sample_upper_bound_after_caps": sum(min(count * gate["maximum_samples_per_candidate_family"], gate["repository_caps"][split]) for count in counts.values())}
    checks = {"all_queries_complete": queries_complete, "train_repository_minimum": split_stats["train"]["unique_repositories"] >= gate["train_minimum_unique_repositories"], "validation_repository_minimum": split_stats["validation"]["unique_repositories"] >= gate["validation_minimum_unique_repositories"], "train_candidate_pr_upper_bound_sufficient": split_stats["train"]["candidate_pr_upper_bound"] >= gate["train_minimum_candidate_pr_upper_bound"], "validation_candidate_pr_upper_bound_sufficient": split_stats["validation"]["candidate_pr_upper_bound"] >= gate["validation_minimum_candidate_pr_upper_bound"], "train_projected_sample_upper_bound_sufficient": split_stats["train"]["projected_sample_upper_bound_after_caps"] >= gate["train_minimum_projected_sample_upper_bound_after_caps"], "validation_projected_sample_upper_bound_sufficient": split_stats["validation"]["projected_sample_upper_bound_after_caps"] >= gate["validation_minimum_projected_sample_upper_bound_after_caps"]}
    return {"unique_candidates": len(records), "unique_repositories": len({row["repository_split_group"] for row in records}), "split_stats": split_stats, "capacity_checks": checks, "github_detail_pilot_capacity_gate_passed": all(checks.values()), "content_download_authorized": False, "training_admitted": False, "gpu_used": False}


def current_commit() -> str:
    commit = os.environ.get("PATCHALIGN_GIT_COMMIT", "").strip() or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid Git commit")
    return commit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_json(args.config)
    deny_config = validate_config(config)
    specs = query_specs(config)
    config_hash = sha256_file(args.config)
    script_hash = sha256_file(Path(__file__))
    commit = current_commit()
    output = Path(config["output_directory"])
    checkpoint_dir = output / "query-checkpoints"
    final_paths = [output / name for name in ("candidates.jsonl", "summary.json", "run-manifest.json")]
    require(not any(path.exists() for path in final_paths), "refusing to overwrite final discovery outputs")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    client = GitHubSearchClient(config["github_issue_linked_cpp"]["api"])
    checkpoints: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        checkpoint_path = checkpoint_dir / f'{spec["query_id"]}.json'
        cached = checkpoint_path.exists()
        if cached:
            checkpoint = load_json(checkpoint_path)
            require(checkpoint["config_sha256"] == config_hash, f"checkpoint config drift: {checkpoint_path}")
            require(checkpoint["script_sha256"] == script_hash, f"checkpoint script drift: {checkpoint_path}")
            require(checkpoint["query"] == spec, f"checkpoint query drift: {checkpoint_path}")
        else:
            response, response_identity = client.search(spec)
            records: list[dict[str, Any]] = []
            rejections: Counter[str] = Counter()
            for item in response.get("items", []):
                record, reason = project_search_item(item, spec["query_id"], deny_config)
                if record is None:
                    rejections[reason] += 1
                else:
                    records.append(record)
            checkpoint = {"version": VERSION, "config_sha256": config_hash, "script_sha256": script_hash, "git_commit": commit, "query": spec, "query_total_count": int(response.get("total_count") or 0), "query_incomplete_results": bool(response.get("incomplete_results")), "returned_items": len(response.get("items", [])), "records": records, "rejections": dict(sorted(rejections.items())), "response_identity": response_identity}
            write_json_atomic(checkpoint_path, checkpoint)
        checkpoints.append(checkpoint)
        print(json.dumps({"query": index, "total": len(specs), "query_id": spec["query_id"], "records": len(checkpoint["records"]), "cached": cached}, sort_keys=True), flush=True)
    records, rejections = merge_checkpoint_records(checkpoints)
    all_complete = len(checkpoints) == len(specs) and not any(row["query_incomplete_results"] for row in checkpoints)
    summary = summarize_capacity(records, config, all_complete)
    summary.update({"version": VERSION, "queries_planned": len(specs), "queries_completed": len(checkpoints), "query_occurrences_returned": sum(row["returned_items"] for row in checkpoints), "query_total_count_sum_non_deduplicated": sum(row["query_total_count"] for row in checkpoints), "rejections": dict(sorted(rejections.items())), "multi_swe_rl_training_repositories": 0, "runbugrun_v2_repository_diversity_credit": 0})
    candidates_path = output / "candidates.jsonl"
    candidates_temporary = candidates_path.with_suffix(".jsonl.tmp")
    candidates_temporary.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    candidates_temporary.replace(candidates_path)
    write_json_atomic(output / "summary.json", summary)
    manifest = {"version": VERSION, "git_commit": commit, "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""), "finished_at": datetime.now(timezone.utc).isoformat(), "config_sha256": config_hash, "script_sha256": script_hash, "decision_sha256": config["decision"]["sha256"], "contract_sha256": config["contract"]["sha256"], "authenticated_github_api": client.authenticated, "query_checkpoint_count": len(checkpoints), "content_boundaries": {"patch_or_source_requested": False, "pr_issue_title_or_body_stored": False, "user_identity_stored": False, "raw_api_response_stored": False, "evaluation_gold_consumed": False}, "outputs": {"candidates.jsonl": {"count": len(records), "sha256": sha256_file(candidates_path)}, "summary.json": {"sha256": sha256_file(output / "summary.json")}}}
    write_json_atomic(output / "run-manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
