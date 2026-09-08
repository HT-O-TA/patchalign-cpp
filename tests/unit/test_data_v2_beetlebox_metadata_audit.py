from __future__ import annotations

from datetime import datetime, timezone

from scripts.data.audit_data_v2_beetlebox_metadata import (
    canonical_github_record_url,
    canonical_repository,
    cap_and_gate,
    parse_updated_files,
    project_record,
)


def config() -> dict:
    return {
        "schema": {
            "language_value": "C++",
            "cpp_extensions": [".cpp", ".hpp"],
        },
        "identity": {
            "repository_resplit_seed": 20260908,
            "validation_percent": 20,
            "maximum_increment_per_repository": {"train": 2, "validation": 2},
        },
        "metadata_gate": {
            "train": {"samples_after_cap": 1, "repositories": 1},
            "validation": {"samples_after_cap": 0, "repositories": 0},
        },
    }


def denylist() -> dict:
    return {
        "repository_matching": {
            "exact_canonical_repositories": ["github.com/blocked/project"],
            "normalized_repository_name_aliases": [],
            "exclude_if_any_normalized_component_contains": [],
        }
    }


def row(**updates: object) -> dict:
    value = {
        "language": "C++",
        "repo_name": "Owner/Repo",
        "repo_url": "https://github.com/Owner/Repo",
        "before_fix_sha": "a" * 40,
        "after_fix_sha": "b" * 40,
        "issue_id": 7,
        "issue_url": "https://github.com/Owner/Repo/issues/7",
        "pull_url": "https://github.com/Owner/Repo/pull/8",
        "updated_files": "['src/a.cpp', 'tests/a.cpp']",
        "report_datetime": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "commit_datetime": datetime(2025, 1, 2, tzinfo=timezone.utc),
    }
    value.update(updates)
    return value


def test_repository_and_record_urls_are_exact() -> None:
    assert canonical_repository("https://github.com/Owner/Repo.git") == "github.com/owner/repo"
    assert canonical_repository("https://gitlab.com/Owner/Repo") is None
    assert canonical_github_record_url(
        "https://github.com/Owner/Repo/issues/7", "github.com/owner/repo", "issues"
    )
    assert not canonical_github_record_url(
        "https://github.com/Other/Repo/issues/7", "github.com/owner/repo", "issues"
    )


def test_updated_files_accepts_json_or_literal_and_rejects_traversal() -> None:
    assert parse_updated_files('["src/a.cpp", "include/a.hpp"]') == ["include/a.hpp", "src/a.cpp"]
    assert parse_updated_files("[{'filename': 'src/a.cpp'}]") == ["src/a.cpp"]
    assert parse_updated_files("['../secret.cpp']") is None
    assert parse_updated_files("not-a-list") is None


def test_projection_is_content_free_and_denylist_is_fail_closed() -> None:
    candidate, reason = project_record(row(), config(), denylist())
    assert reason is None and candidate is not None
    assert set(candidate) == {
        "stable_id", "repository", "before", "after", "issue_id", "updated_file_count",
        "cpp_file_count", "report_time", "commit_time",
    }
    blocked, reason = project_record(
        row(
            repo_name="blocked/project",
            repo_url="https://github.com/blocked/project",
            issue_url="https://github.com/blocked/project/issues/7",
            pull_url="https://github.com/blocked/project/pull/8",
        ),
        config(), denylist(),
    )
    assert blocked is None and reason == "evaluation_repository_denylist"


def test_wrong_language_sha_and_non_cpp_are_rejected() -> None:
    assert project_record(row(language="Python"), config(), denylist())[1] == "language_mismatch"
    assert project_record(row(before_fix_sha="bad"), config(), denylist())[1] == "before_sha_invalid"
    assert project_record(row(updated_files="['README.md']"), config(), denylist())[1] == "no_cpp_updated_file"


def test_repository_resplit_and_cap_are_deterministic() -> None:
    candidates = []
    for index in range(5):
        candidate, reason = project_record(
            row(
                before_fix_sha=f"{index + 1:040x}",
                after_fix_sha=f"{index + 11:040x}",
                issue_id=index + 1,
                issue_url=f"https://github.com/Owner/Repo/issues/{index + 1}",
            ),
            config(), denylist(),
        )
        assert reason is None and candidate is not None
        candidates.append(candidate)
    assert cap_and_gate(candidates, config()) == cap_and_gate(reversed(candidates), config())
    report = cap_and_gate(candidates, config())
    assert sum(report[split]["actual"]["samples_after_cap"] for split in ("train", "validation")) == 2
