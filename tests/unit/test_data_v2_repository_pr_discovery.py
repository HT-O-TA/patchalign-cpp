from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.discover_data_v2_repository_prs import (
    project_pull_request_item,
    project_repository_item,
    pull_request_query_spec,
    repository_query_specs,
    select_repositories,
    summarize_capacity,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_repository_pr_discovery_v2.json").read_text(encoding="utf-8"))


def deny_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_metadata_pilot_v1_2.json").read_text(encoding="utf-8"))


def repository_item(owner: str = "fresh", repo: str = "project", stars: int = 50) -> dict:
    return {
        "full_name": f"{owner}/{repo}",
        "fork": False,
        "archived": False,
        "language": "C++",
        "stargazers_count": stars,
        "pushed_at": "2026-01-01T00:00:00Z",
        "description": "must not be projected",
        "owner": {"login": "must-not-be-projected"},
        "topics": ["must-not-be-projected"],
        "license": {"spdx_id": "MIT"},
    }


def pull_item(repository: str = "github.com/fresh/project", number: int = 17) -> dict:
    owner_repo = repository.removeprefix("github.com/")
    base = f"https://api.github.com/repos/{owner_repo}"
    return {
        "repository_url": base,
        "number": number,
        "pull_request": {"url": f"{base}/pulls/{number}"},
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-02T00:00:00Z",
        "closed_at": "2020-01-03T00:00:00Z",
        "title": "must not be projected",
        "body": "must not be projected",
        "labels": [{"name": "bug"}],
        "user": {"login": "must-not-be-projected"},
    }


def selected_repository(repository: str = "github.com/fresh/project", split: str = "train") -> dict:
    return {
        "repository_candidate_id": "ghrepo-test",
        "repository_split_group": repository,
        "repository_stars_at_discovery": 50,
        "repository_pushed_at": "2026-01-01T00:00:00Z",
        "source_query_ids": ["repo-page-01"],
        "training_admitted": False,
        "projected_split": split,
        "selection_rank_sha256": "sha256:" + "0" * 64,
    }


def test_v2_contract_is_fail_closed_and_metadata_only() -> None:
    config = load_config()
    validate_config(config)
    assert config["scope"] == {
        "metadata_only": True,
        "patch_or_source_download_authorized": False,
        "training_dataset_freeze_authorized": False,
        "gpu_authorized": False,
        "dpo_authorized": False,
    }
    assert config["github"]["api"]["maximum_search_requests"] == 250


def test_two_stage_query_matrix_uses_endpoint_appropriate_qualifiers() -> None:
    config = load_config()
    repository_specs = repository_query_specs(config)
    assert len(repository_specs) == 10
    assert repository_specs[0]["endpoint"] == "/search/repositories"
    assert repository_specs[0]["parameters"]["page"] == 1
    assert repository_specs[-1]["parameters"]["page"] == 10
    repository_query = repository_specs[0]["parameters"]["q"]
    assert "language:C++" in repository_query
    assert "stars:>=20" in repository_query
    assert "archived:false" in repository_query

    spec = pull_request_query_spec(selected_repository(), config)
    assert spec["endpoint"] == "/search/issues"
    query = spec["parameters"]["q"]
    assert query.startswith("repo:fresh/project ")
    assert "is:pr" in query and "is:merged" in query and "linked:issue" in query
    assert "language:" not in query and "stars:" not in query and "archived:" not in query


def test_repository_projection_and_integrity_gates() -> None:
    record, reason = project_repository_item(repository_item(), "repo-page-01", deny_config())
    assert reason == "selected"
    assert record is not None
    assert set(record) == {
        "repository_candidate_id",
        "repository_split_group",
        "repository_stars_at_discovery",
        "repository_pushed_at",
        "source_query_ids",
        "training_admitted",
    }
    assert not {"description", "owner", "topics", "license"}.intersection(record)

    denied, reason = project_repository_item(repository_item("bitcoin", "bitcoin"), "repo-page-01", deny_config())
    assert denied is None and reason == "reserved_repository"
    fork = repository_item()
    fork["fork"] = True
    assert project_repository_item(fork, "repo-page-01", deny_config())[1] == "fork"
    wrong_language = repository_item()
    wrong_language["language"] = "Python"
    assert project_repository_item(wrong_language, "repo-page-01", deny_config())[1] == "primary_language_not_cpp"


def test_pull_request_projection_drops_sensitive_fields() -> None:
    repository = selected_repository()
    record, reason = project_pull_request_item(pull_item(), repository, "ghrepo-test")
    assert reason == "selected"
    assert record is not None
    assert set(record) == {
        "candidate_id",
        "source_dataset",
        "repository_split_group",
        "repository_stars_at_discovery",
        "projected_split",
        "pr_number",
        "pr_api_url",
        "created_at",
        "updated_at",
        "closed_at",
        "query_id",
        "sampling_family_status",
        "training_admitted",
    }
    assert not {"title", "body", "labels", "user"}.intersection(record)
    mismatched, reason = project_pull_request_item(
        pull_item("github.com/other/repo"), repository, "ghrepo-test"
    )
    assert mismatched is None and reason == "repository_identity_mismatch"


def test_fixed_repository_selection_uses_contract_split_and_hash_rank() -> None:
    repositories = []
    for index in range(4000):
        item = repository_item("capacity", f"repo-{index:04d}", 100 + index)
        record, reason = project_repository_item(item, "repo-page-01", deny_config())
        assert reason == "selected" and record is not None
        repositories.append(record)
    selected = select_repositories(repositories, load_config())
    assert len(selected) == 240
    assert sum(row["projected_split"] == "train" for row in selected) == 200
    assert sum(row["projected_split"] == "validation" for row in selected) == 40
    assert selected == select_repositories(list(reversed(repositories)), load_config())
    assert len({row["repository_split_group"] for row in selected}) == 240


def candidate(repository: str, split: str, number: int) -> dict:
    return {
        "candidate_id": f"{repository}-{number}",
        "repository_split_group": repository,
        "projected_split": split,
    }


def test_capacity_gate_uses_repositories_with_candidates_and_caps() -> None:
    rows = []
    for repo in range(100):
        rows.extend(candidate(f"github.com/train/repo-{repo}", "train", number) for number in range(10))
    for repo in range(20):
        rows.extend(candidate(f"github.com/validation/repo-{repo}", "validation", number) for number in range(5))
    summary = summarize_capacity(rows, load_config(), True)
    assert summary["split_stats"]["train"] == {
        "unique_repositories_with_candidates": 100,
        "candidate_pr_upper_bound": 1000,
        "projected_sample_upper_bound_after_caps": 2000,
    }
    assert summary["split_stats"]["validation"] == {
        "unique_repositories_with_candidates": 20,
        "candidate_pr_upper_bound": 100,
        "projected_sample_upper_bound_after_caps": 200,
    }
    assert summary["github_detail_pilot_capacity_gate_passed"] is True
    assert summarize_capacity(rows, load_config(), False)["github_detail_pilot_capacity_gate_passed"] is False


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("output_directory",), "/tmp/drift"),
        (("scope", "gpu_authorized"), True),
        (("scope", "patch_or_source_download_authorized"), True),
        (("github", "api", "maximum_search_requests"), 251),
        (("github", "repository_search", "endpoint"), "/search/issues"),
        (("github", "repository_search", "query"), "language:C++"),
        (("github", "repository_selection", "train_repositories"), 199),
        (("github", "pull_request_search", "query_template"), "is:pr"),
        (("github", "capacity_gate", "train_minimum_unique_repositories_with_candidates"), 99),
        (("legacy_denylist", "complete_for_patch_content_admission"), True),
    ],
)
def test_v2_contract_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(load_config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
