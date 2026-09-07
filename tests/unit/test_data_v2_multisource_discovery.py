from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.check_data_v2_contract import assign_new_split
from scripts.data.discover_data_v2_multisource import (
    project_search_item,
    query_specs,
    summarize_capacity,
    validate_config,
)

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_multisource_discovery_v1.json").read_text(encoding="utf-8"))


def deny_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_metadata_pilot_v1_2.json").read_text(encoding="utf-8"))


def search_item(owner: str = "fresh", repo: str = "project", number: int = 17) -> dict:
    return {
        "repository_url": f"https://api.github.com/repos/{owner}/{repo}",
        "number": number,
        "pull_request": {"url": f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"},
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-02T00:00:00Z",
        "closed_at": "2020-01-03T00:00:00Z",
        "title": "must not be projected",
        "body": "must not be projected",
        "user": {"login": "must-not-be-projected"},
        "labels": [{"name": "bug"}],
    }


def test_multisource_contract_is_fail_closed() -> None:
    config = load_config()
    validate_config(config)
    assert config["scope"]["gpu_authorized"] is False
    assert config["scope"]["dpo_authorized"] is False
    assert config["multi_swe_rl"]["all_cpp_repositories_reserved"] is True
    assert config["runbugrun_v2"]["release_asset"]["size_bytes"] == 120501798


def test_query_matrix_is_exact_and_bounded() -> None:
    specs = query_specs(load_config())
    assert len(specs) == 64
    assert specs[0]["query_id"] == "q00-asc"
    assert specs[0]["window_start"] == "2018-01-01"
    assert specs[0]["window_end"] == "2018-03-31"
    assert specs[-1]["query_id"] == "q31-desc"
    assert specs[-1]["window_start"] == "2025-10-01"
    assert specs[-1]["window_end"] == "2025-12-31"
    assert all(spec["per_page"] == 100 and spec["page"] == 1 for spec in specs)


def test_projection_drops_sensitive_fields_and_reserved_repositories() -> None:
    record, reason = project_search_item(search_item(), "q00-asc", deny_config())
    assert reason == "selected"
    assert record is not None
    assert set(record) == {
        "candidate_id",
        "source_dataset",
        "repository_split_group",
        "pr_number",
        "pr_api_url",
        "created_at",
        "updated_at",
        "closed_at",
        "query_ids",
        "sampling_family_status",
        "training_admitted",
    }
    assert not {"title", "body", "user", "labels"}.intersection(record)
    denied, reason = project_search_item(search_item("bitcoin", "bitcoin"), "q00-asc", deny_config())
    assert denied is None
    assert reason == "reserved_repository"


def test_capacity_gate_uses_actual_hash_splits_and_caps() -> None:
    config = load_config()
    contract = json.loads((ROOT / config["contract"]["path"]).read_text(encoding="utf-8"))
    train_repos: list[str] = []
    validation_repos: list[str] = []
    index = 0
    while len(train_repos) < 100 or len(validation_repos) < 20:
        repository = f"github.com/capacity/repo-{index:04d}"
        split = assign_new_split(repository, 10, contract["split"]["hash_seed"])
        target = train_repos if split == "train" else validation_repos
        limit = 100 if split == "train" else 20
        if len(target) < limit:
            target.append(repository)
        index += 1
    records = []
    for repository in train_repos:
        for number in range(10):
            records.append({"repository_split_group": repository, "candidate_id": f"{repository}-{number}"})
    for repository in validation_repos:
        for number in range(5):
            records.append({"repository_split_group": repository, "candidate_id": f"{repository}-{number}"})
    summary = summarize_capacity(records, config, True)
    assert summary["split_stats"]["train"] == {
        "unique_repositories": 100,
        "candidate_pr_upper_bound": 1000,
        "projected_sample_upper_bound_after_caps": 2000,
    }
    assert summary["split_stats"]["validation"] == {
        "unique_repositories": 20,
        "candidate_pr_upper_bound": 100,
        "projected_sample_upper_bound_after_caps": 200,
    }
    assert summary["github_detail_pilot_capacity_gate_passed"] is True
    assert summary["content_download_authorized"] is False


def test_capacity_gate_rejects_partial_queries() -> None:
    summary = summarize_capacity([], load_config(), False)
    assert summary["github_detail_pilot_capacity_gate_passed"] is False
    assert summary["capacity_checks"]["all_queries_complete"] is False


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("output_directory",), "/tmp/drift"),
        (("scope", "gpu_authorized"), True),
        (("scope", "patch_or_source_download_authorized"), True),
        (("github_issue_linked_cpp", "api", "maximum_search_requests"), 65),
        (("github_issue_linked_cpp", "search", "start_date"), "2017-01-01"),
        (("github_issue_linked_cpp", "capacity_gate", "train_minimum_unique_repositories"), 99),
        (("multi_swe_rl", "all_cpp_repositories_reserved"), False),
        (("runbugrun_v2", "release_asset", "size_bytes"), 1),
        (("runbugrun_v2", "release_download_requires_new_contract"), False),
    ],
)
def test_multisource_contract_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(load_config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
