#!/usr/bin/env python3
"""Two-stage, metadata-only GitHub repository and linked-PR discovery."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
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
from scripts.data.check_data_v2_evaluation_denylist import repository_denial_reason


VERSION = "data-v2-repository-pr-discovery-v2.1"
DEFAULT_CONFIG = Path("configs/data/data_v2_repository_pr_discovery_v2_1.json")


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
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_bound_file(spec: dict[str, str], label: str) -> dict[str, Any]:
    path = Path(spec["path"])
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return load_json(path) if path.suffix == ".json" else {}


def repository_query_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config["github"]["repository_search"]
    return [
        {
            "query_id": f"repo-page-{page:02d}",
            "endpoint": search["endpoint"],
            "parameters": {
                "q": search["query"],
                "sort": search["sort"],
                "order": search["order"],
                "per_page": search["per_page"],
                "page": page,
            },
        }
        for page in range(1, search["pages"] + 1)
    ]


def pull_request_query_spec(repository: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    search = config["github"]["pull_request_search"]
    owner_repo = repository["repository_split_group"].removeprefix("github.com/")
    query = search["query_template"].format(owner_repo=owner_repo)
    return {
        "query_id": repository["repository_candidate_id"],
        "endpoint": search["endpoint"],
        "repository_split_group": repository["repository_split_group"],
        "projected_split": repository["projected_split"],
        "parameters": {
            "q": query,
            "sort": search["sort"],
            "order": search["order"],
            "per_page": search["per_page"],
            "page": search["page"],
        },
    }


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    require(config.get("version") == VERSION, "unexpected discovery version")
    contract = verify_bound_file(config["contract"], "Data-v2 contract")
    validate_contract(contract)
    verify_bound_file(config["decision"], "ADR-0016")
    deny_config = verify_bound_file(config["evaluation_denylist"], "evaluation denylist")
    require(
        deny_config["scope"]["complete_for_candidate_content_acquisition"] is True,
        "evaluation denylist is incomplete",
    )
    require(
        config["evaluation_denylist"]["complete_for_candidate_content_acquisition"] is True,
        "content-acquisition completeness not bound",
    )
    require(
        config["scope"]
        == {
            "metadata_only": True,
            "patch_or_source_download_authorized": False,
            "training_dataset_freeze_authorized": False,
            "gpu_authorized": False,
            "dpo_authorized": False,
        },
        "discovery scope changed",
    )
    require(config["supersedes"]["jobs"] == [96922], "superseded job evidence changed")

    github = config["github"]
    api = github["api"]
    require(api["base_url"] == "https://api.github.com", "unexpected API base")
    require(api["timeout_seconds"] == 30, "timeout changed")
    require(api["maximum_attempts"] == 3, "retry bound changed")
    require(api["minimum_request_interval_seconds"] >= 7.0, "search throttle weakened")
    require(api["maximum_search_requests"] == 250, "request budget changed")

    repository_search = github["repository_search"]
    require(repository_search["endpoint"] == "/search/repositories", "wrong repository endpoint")
    require(
        repository_search["query"]
        == "language:C++ stars:>=20 archived:false pushed:>=2018-01-01",
        "repository query changed",
    )
    require(repository_search["sort"] == "stars" and repository_search["order"] == "desc", "repository order changed")
    require(repository_search["per_page"] == 100 and repository_search["pages"] == 10, "repository page budget changed")
    for key in (
        "default_excludes_forks",
        "require_returned_language_cpp",
        "require_returned_not_archived",
        "require_returned_not_fork",
    ):
        require(repository_search[key] is True, f"repository integrity gate disabled: {key}")

    selection = github["repository_selection"]
    require(selection["ranking"] == "sha256(seed_nul_repository_split_group)", "selection ranking changed")
    require(selection["train_repositories"] == 200, "train repository target changed")
    require(selection["validation_repositories"] == 40, "validation repository target changed")
    require(selection["existing_contract_hash_split_required"] is True, "contract split disabled")

    pull_search = github["pull_request_search"]
    require(pull_search["endpoint"] == "/search/issues", "wrong PR endpoint")
    require(
        pull_search["query_template"]
        == "repo:{owner_repo} is:pr is:merged linked:issue merged:2018-01-01..2025-12-31",
        "PR query changed",
    )
    require(pull_search["sort"] == "created" and pull_search["order"] == "desc", "PR order changed")
    require(pull_search["per_page"] == 100 and pull_search["page"] == 1, "PR page budget changed")

    projection = github["projection"]
    require(
        projection
        == {
            "store_repository_identity": True,
            "store_repository_star_snapshot": True,
            "store_pr_number_and_api_url": True,
            "store_timestamps": True,
            "store_title_body_labels_user": False,
            "store_patch_or_source": False,
            "store_raw_response": False,
            "store_response_sha256": True,
        },
        "projection changed",
    )
    for forbidden in ("store_title_body_labels_user", "store_patch_or_source", "store_raw_response"):
        require(projection[forbidden] is False, f"forbidden projection enabled: {forbidden}")

    gate = github["capacity_gate"]
    require(
        gate
        == {
            "all_queries_complete_required": True,
            "train_minimum_unique_repositories_with_candidates": 100,
            "validation_minimum_unique_repositories_with_candidates": 20,
            "train_minimum_candidate_pr_upper_bound": 1000,
            "validation_minimum_candidate_pr_upper_bound": 100,
            "train_minimum_projected_sample_upper_bound_after_caps": 2000,
            "validation_minimum_projected_sample_upper_bound_after_caps": 200,
            "maximum_samples_per_candidate_family": 2,
            "repository_caps": {"train": 40, "validation": 20},
        },
        "capacity gate changed",
    )
    planned_requests = repository_search["pages"] + selection["train_repositories"] + selection["validation_repositories"]
    require(planned_requests == api["maximum_search_requests"], "request budget does not match query matrix")
    require(config["output_directory"] == "artifacts/data-v2/repository-pr-discovery-v2-1", "output directory changed")
    return deny_config


def is_denied_repository(canonical: str, deny_config: dict[str, Any]) -> bool:
    return repository_denial_reason(canonical, deny_config) is not None


def project_repository_item(
    item: dict[str, Any], query_id: str, deny_config: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    full_name = str(item.get("full_name") or "")
    if not re.fullmatch(r"[^/]+/[^/]+", full_name):
        return None, "invalid_repository_identity"
    canonical = canonical_repository("github.com/" + full_name)
    if is_denied_repository(canonical, deny_config):
        return None, "reserved_repository"
    if item.get("fork") is not False:
        return None, "fork"
    if item.get("archived") is not False:
        return None, "archived"
    if item.get("language") != "C++":
        return None, "primary_language_not_cpp"
    stars = int(item.get("stargazers_count") or 0)
    if stars < 20:
        return None, "insufficient_stars"
    candidate_id = "ghrepo-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    record = {
        "repository_candidate_id": candidate_id,
        "repository_split_group": canonical,
        "repository_stars_at_discovery": stars,
        "repository_pushed_at": item.get("pushed_at"),
        "source_query_ids": [query_id],
        "training_admitted": False,
    }
    require(
        not {"description", "owner", "topics", "license", "homepage"}.intersection(record),
        "unapproved repository field entered projection",
    )
    return record, "selected"


def select_repositories(
    repositories: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    contract = load_json(Path(config["contract"]["path"]))
    seed = contract["split"]["hash_seed"]
    validation_percent = contract["split"]["new_split_group_validation_percent"]
    selection = config["github"]["repository_selection"]
    by_split: dict[str, list[dict[str, Any]]] = {"train": [], "validation": []}
    for row in repositories:
        copied = dict(row)
        split = assign_new_split(copied["repository_split_group"], validation_percent, seed)
        copied["projected_split"] = split
        copied["selection_rank_sha256"] = sha256_bytes(
            f'{seed}\0{copied["repository_split_group"]}'.encode("utf-8")
        )
        by_split[split].append(copied)
    selected: list[dict[str, Any]] = []
    for split in ("train", "validation"):
        target = selection[f"{split}_repositories"]
        ranked = sorted(
            by_split[split],
            key=lambda row: (row["selection_rank_sha256"], row["repository_split_group"]),
        )
        require(len(ranked) >= target, f"insufficient {split} repository pool: {len(ranked)} < {target}")
        selected.extend(ranked[:target])
    return sorted(selected, key=lambda row: (row["projected_split"], row["selection_rank_sha256"]))


def project_pull_request_item(
    item: dict[str, Any], repository: dict[str, Any], query_id: str
) -> tuple[dict[str, Any] | None, str]:
    repository_url = str(item.get("repository_url") or "")
    expected_url = "https://api.github.com/repos/" + repository["repository_split_group"].removeprefix("github.com/")
    if repository_url.casefold() != expected_url.casefold():
        return None, "repository_identity_mismatch"
    pull_url = str((item.get("pull_request") or {}).get("url") or "")
    if not pull_url.casefold().startswith((expected_url + "/pulls/").casefold()):
        return None, "missing_pull_request_api_url"
    number = int(item.get("number") or 0)
    if number <= 0:
        return None, "invalid_pr_number"
    canonical = repository["repository_split_group"]
    candidate_id = "ghpr-" + hashlib.sha256(f"{canonical}\0{number}".encode("utf-8")).hexdigest()[:24]
    record = {
        "candidate_id": candidate_id,
        "source_dataset": "github-linked-pr-discovery-v2.1",
        "repository_split_group": canonical,
        "repository_stars_at_discovery": repository["repository_stars_at_discovery"],
        "projected_split": repository["projected_split"],
        "pr_number": number,
        "pr_api_url": pull_url,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "closed_at": item.get("closed_at"),
        "query_id": query_id,
        "sampling_family_status": "candidate_one_pr_upper_bound",
        "training_admitted": False,
    }
    require(
        not {"title", "body", "labels", "user", "assignee", "author_association"}.intersection(record),
        "sensitive PR field entered projection",
    )
    return record, "selected"


class GitHubSearchClient:
    def __init__(self, api: dict[str, Any]) -> None:
        self.api = api
        token = os.environ.get(api["token_environment_variable"], "").strip()
        self.authenticated = bool(token)
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": api["user_agent"],
            "X-GitHub-Api-Version": api["version"],
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.last_request: float | None = None

    def search(self, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        url = self.api["base_url"] + spec["endpoint"] + "?" + urllib.parse.urlencode(spec["parameters"])
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
                    headers = {
                        key: response.headers.get(key, "")
                        for key in (
                            "ETag",
                            "X-RateLimit-Limit",
                            "X-RateLimit-Remaining",
                            "X-RateLimit-Reset",
                            "X-RateLimit-Resource",
                        )
                    }
                    return json.loads(raw), {"url": url, "sha256": sha256_bytes(raw), "headers": headers}
            except urllib.error.HTTPError as error:
                if error.code not in {403, 429, 500, 502, 503, 504} or attempt + 1 == self.api["maximum_attempts"]:
                    raise RuntimeError(f"GitHub search HTTP {error.code}: {url}") from error
            except urllib.error.URLError as error:
                if attempt + 1 == self.api["maximum_attempts"]:
                    raise RuntimeError(f"GitHub search unavailable: {error.reason}") from error
            time.sleep(2**attempt)
        raise AssertionError("unreachable")


def merge_repository_checkpoints(checkpoints: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    merged: dict[str, dict[str, Any]] = {}
    rejections: Counter[str] = Counter()
    for checkpoint in checkpoints:
        rejections.update(checkpoint["rejections"])
        for row in checkpoint["records"]:
            key = row["repository_split_group"]
            if key not in merged:
                merged[key] = dict(row)
            else:
                merged[key]["source_query_ids"] = sorted(
                    set(merged[key]["source_query_ids"]) | set(row["source_query_ids"])
                )
    return sorted(merged.values(), key=lambda row: row["repository_split_group"]), rejections


def merge_pr_checkpoints(checkpoints: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    merged: dict[str, dict[str, Any]] = {}
    rejections: Counter[str] = Counter()
    for checkpoint in checkpoints:
        rejections.update(checkpoint["rejections"])
        for row in checkpoint["records"]:
            require(row["candidate_id"] not in merged, f'duplicate PR candidate: {row["candidate_id"]}')
            merged[row["candidate_id"]] = row
    return sorted(merged.values(), key=lambda row: (row["repository_split_group"], row["pr_number"])), rejections


def summarize_capacity(
    candidates: list[dict[str, Any]], config: dict[str, Any], all_queries_complete: bool
) -> dict[str, Any]:
    by_split_repo: dict[str, dict[str, int]] = {"train": defaultdict(int), "validation": defaultdict(int)}
    for row in candidates:
        by_split_repo[row["projected_split"]][row["repository_split_group"]] += 1
    gate = config["github"]["capacity_gate"]
    split_stats: dict[str, dict[str, int]] = {}
    for split in ("train", "validation"):
        counts = by_split_repo[split]
        split_stats[split] = {
            "unique_repositories_with_candidates": len(counts),
            "candidate_pr_upper_bound": sum(counts.values()),
            "projected_sample_upper_bound_after_caps": sum(
                min(
                    count * gate["maximum_samples_per_candidate_family"],
                    gate["repository_caps"][split],
                )
                for count in counts.values()
            ),
        }
    checks = {
        "all_queries_complete": all_queries_complete,
        "train_repository_minimum": split_stats["train"]["unique_repositories_with_candidates"]
        >= gate["train_minimum_unique_repositories_with_candidates"],
        "validation_repository_minimum": split_stats["validation"]["unique_repositories_with_candidates"]
        >= gate["validation_minimum_unique_repositories_with_candidates"],
        "train_candidate_pr_upper_bound_sufficient": split_stats["train"]["candidate_pr_upper_bound"]
        >= gate["train_minimum_candidate_pr_upper_bound"],
        "validation_candidate_pr_upper_bound_sufficient": split_stats["validation"]["candidate_pr_upper_bound"]
        >= gate["validation_minimum_candidate_pr_upper_bound"],
        "train_projected_sample_upper_bound_sufficient": split_stats["train"]["projected_sample_upper_bound_after_caps"]
        >= gate["train_minimum_projected_sample_upper_bound_after_caps"],
        "validation_projected_sample_upper_bound_sufficient": split_stats["validation"]["projected_sample_upper_bound_after_caps"]
        >= gate["validation_minimum_projected_sample_upper_bound_after_caps"],
    }
    return {
        "unique_candidates": len(candidates),
        "split_stats": split_stats,
        "capacity_checks": checks,
        "github_detail_pilot_capacity_gate_passed": all(checks.values()),
        "content_download_authorized": False,
        "training_admitted": False,
        "gpu_used": False,
    }


def current_commit() -> str:
    commit = os.environ.get("PATCHALIGN_GIT_COMMIT", "").strip() or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid Git commit")
    return commit


def execute_query(
    spec: dict[str, Any],
    checkpoint_path: Path,
    client: GitHubSearchClient,
    config_hash: str,
    script_hash: str,
    commit: str,
    projector: Any,
) -> tuple[dict[str, Any], bool]:
    cached = checkpoint_path.exists()
    if cached:
        checkpoint = load_json(checkpoint_path)
        require(checkpoint["config_sha256"] == config_hash, f"checkpoint config drift: {checkpoint_path}")
        require(checkpoint["script_sha256"] == script_hash, f"checkpoint script drift: {checkpoint_path}")
        require(checkpoint["query"] == spec, f"checkpoint query drift: {checkpoint_path}")
        return checkpoint, True
    response, response_identity = client.search(spec)
    records: list[dict[str, Any]] = []
    rejections: Counter[str] = Counter()
    for item in response.get("items", []):
        record, reason = projector(item)
        if record is None:
            rejections[reason] += 1
        else:
            records.append(record)
    checkpoint = {
        "version": VERSION,
        "config_sha256": config_hash,
        "script_sha256": script_hash,
        "git_commit": commit,
        "query": spec,
        "query_total_count": int(response.get("total_count") or 0),
        "query_incomplete_results": bool(response.get("incomplete_results")),
        "returned_items": len(response.get("items", [])),
        "records": records,
        "rejections": dict(sorted(rejections.items())),
        "response_identity": response_identity,
    }
    write_json_atomic(checkpoint_path, checkpoint)
    return checkpoint, False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_json(args.config)
    deny_config = validate_config(config)
    config_hash = sha256_file(args.config)
    script_hash = sha256_file(Path(__file__))
    commit = current_commit()
    output = Path(config["output_directory"])
    final_names = (
        "repository-pool.jsonl",
        "selected-repositories.jsonl",
        "candidates.jsonl",
        "summary.json",
        "run-manifest.json",
    )
    require(not any((output / name).exists() for name in final_names), "refusing to overwrite final outputs")
    repository_checkpoint_dir = output / "repository-query-checkpoints"
    pr_checkpoint_dir = output / "pr-query-checkpoints"
    repository_checkpoint_dir.mkdir(parents=True, exist_ok=True)
    pr_checkpoint_dir.mkdir(parents=True, exist_ok=True)
    client = GitHubSearchClient(config["github"]["api"])

    repository_specs = repository_query_specs(config)
    repository_checkpoints: list[dict[str, Any]] = []
    for index, spec in enumerate(repository_specs, start=1):
        checkpoint, cached = execute_query(
            spec,
            repository_checkpoint_dir / f'{spec["query_id"]}.json',
            client,
            config_hash,
            script_hash,
            commit,
            lambda item, query_id=spec["query_id"]: project_repository_item(item, query_id, deny_config),
        )
        repository_checkpoints.append(checkpoint)
        print(
            json.dumps(
                {
                    "stage": "repository",
                    "query": index,
                    "total": len(repository_specs),
                    "records": len(checkpoint["records"]),
                    "cached": cached,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    repository_pool, repository_rejections = merge_repository_checkpoints(repository_checkpoints)
    selected_repositories = select_repositories(repository_pool, config)

    pr_checkpoints: list[dict[str, Any]] = []
    for index, repository in enumerate(selected_repositories, start=1):
        spec = pull_request_query_spec(repository, config)
        checkpoint, cached = execute_query(
            spec,
            pr_checkpoint_dir / f'{spec["query_id"]}.json',
            client,
            config_hash,
            script_hash,
            commit,
            lambda item, repo=repository, query_id=spec["query_id"]: project_pull_request_item(
                item, repo, query_id
            ),
        )
        pr_checkpoints.append(checkpoint)
        print(
            json.dumps(
                {
                    "stage": "pull_request",
                    "query": index,
                    "total": len(selected_repositories),
                    "repository": repository["repository_split_group"],
                    "records": len(checkpoint["records"]),
                    "cached": cached,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    candidates, pr_rejections = merge_pr_checkpoints(pr_checkpoints)
    all_checkpoints = repository_checkpoints + pr_checkpoints
    all_queries_complete = (
        len(all_checkpoints) == config["github"]["api"]["maximum_search_requests"]
        and not any(checkpoint["query_incomplete_results"] for checkpoint in all_checkpoints)
    )
    summary = summarize_capacity(candidates, config, all_queries_complete)
    summary.update(
        {
            "version": VERSION,
            "repository_search_queries": len(repository_checkpoints),
            "pr_search_queries": len(pr_checkpoints),
            "queries_completed": len(all_checkpoints),
            "repository_pool_count": len(repository_pool),
            "selected_repository_count": len(selected_repositories),
            "selected_repository_split_counts": dict(
                sorted(Counter(row["projected_split"] for row in selected_repositories).items())
            ),
            "repository_rejections": dict(sorted(repository_rejections.items())),
            "pr_rejections": dict(sorted(pr_rejections.items())),
        }
    )

    repository_pool_path = output / "repository-pool.jsonl"
    selected_path = output / "selected-repositories.jsonl"
    candidates_path = output / "candidates.jsonl"
    summary_path = output / "summary.json"
    write_jsonl_atomic(repository_pool_path, repository_pool)
    write_jsonl_atomic(selected_path, selected_repositories)
    write_jsonl_atomic(candidates_path, candidates)
    write_json_atomic(summary_path, summary)
    manifest = {
        "version": VERSION,
        "git_commit": commit,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": config_hash,
        "script_sha256": script_hash,
        "decision_sha256": config["decision"]["sha256"],
        "contract_sha256": config["contract"]["sha256"],
        "authenticated_github_api": client.authenticated,
        "checkpoint_counts": {
            "repository": len(repository_checkpoints),
            "pull_request": len(pr_checkpoints),
        },
        "content_boundaries": {
            "patch_or_source_requested": False,
            "pr_issue_title_or_body_stored": False,
            "user_identity_stored": False,
            "raw_api_response_stored": False,
            "evaluation_gold_consumed": False,
        },
        "outputs": {
            "repository-pool.jsonl": {
                "count": len(repository_pool),
                "sha256": sha256_file(repository_pool_path),
            },
            "selected-repositories.jsonl": {
                "count": len(selected_repositories),
                "sha256": sha256_file(selected_path),
            },
            "candidates.jsonl": {
                "count": len(candidates),
                "sha256": sha256_file(candidates_path),
            },
            "summary.json": {"sha256": sha256_file(summary_path)},
        },
    }
    write_json_atomic(output / "run-manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
