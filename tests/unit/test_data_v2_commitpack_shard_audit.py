from __future__ import annotations

from collections import Counter

from scripts.data.audit_data_v2_commitpack_shard import (
    assign_split,
    canonical_repository,
    changed_analysis,
    project_candidate,
    public_projection,
    retain_best,
    share_gate,
)


def config() -> dict:
    return {
        "schema": {
            "required_fields": [
                "commit", "old_file", "new_file", "old_contents", "new_contents",
                "subject", "message", "lang", "license", "repos",
            ],
            "language": "c++",
            "cpp_extensions": [".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"],
            "minimum_changed_logical_lines": 2,
            "maximum_changed_logical_lines": 200,
        },
        "license": {"allowed_spdx": ["MIT", "Apache-2.0"]},
        "features": {
            "long_code_min_lines": 100,
            "long_prompt_min_estimated_tokens": 1024,
            "bug_fix_terms": ["bug", "fix", "crash"],
        },
        "identity": {
            "split_seed": 20260906,
            "new_repository_validation_percent": 10,
            "maximum_samples_per_sampling_family_across_v1_plus_increment": 2,
            "maximum_increment_per_repository": {"train": 40, "validation": 20},
        },
        "static_share_gate": {
            "train": {"samples": 1, "new_repositories": 1, "sampling_families": 1},
            "validation": {"samples": 1, "new_repositories": 1, "sampling_families": 1},
        },
    }


def denylist() -> dict:
    return {
        "repository_matching": {
            "exact_canonical_repositories": ["github.com/llvm/llvm-project"],
            "normalized_repository_name_aliases": ["cppcheck"],
            "exclude_if_any_normalized_component_contains": ["leetcode"],
        }
    }


def row(**updates: object) -> dict:
    value = {
        "commit": "a" * 40,
        "old_file": "src/example.cpp",
        "new_file": "src/example.cpp",
        "old_contents": "int f() {\n  int x = 0;\n  return x;\n}\n",
        "new_contents": "int f() {\n  int x = 1;\n  return x + 1;\n}\n",
        "subject": "fix incorrect result",
        "message": "bug fix",
        "lang": "c++",
        "license": "mit",
        "repos": "Owner/Repo",
    }
    value.update(updates)
    return value


def state() -> tuple[dict, dict, dict]:
    frozen = {
        "split_by_repo": {},
        "frozen_family_counts": Counter(),
        "frozen_repositories": set(),
    }
    legacy = {"payloads": set(), "commits": set(), "paths": set()}
    seen = {"payloads": set(), "commits": set(), "paths": set()}
    return frozen, legacy, seen


def test_repository_identity_requires_one_canonical_github_repo() -> None:
    assert canonical_repository("Owner/Repo") == "github.com/owner/repo"
    assert canonical_repository("https://github.com/Owner/Repo.git") == "github.com/owner/repo"
    assert canonical_repository("Owner/Repo, Fork/Repo") is None
    assert canonical_repository("Owner/Repo, Fork/Repo", require_single=False) == "github.com/owner/repo"


def test_changed_analysis_uses_max_add_delete_and_stable_anchor() -> None:
    first = changed_analysis("a\nb\nc\n", "a\nx\ny\nc\n")
    second = changed_analysis("a\nb\nc\n", "a\nx\ny\nc\n")
    assert first == second
    assert first[0] == 2
    assert first[1] == [2]
    assert len(first[2]) == 64


def test_candidate_is_content_free_after_projection_and_deterministic() -> None:
    frozen, legacy, seen = state()
    candidate, reason = project_candidate(row(), config(), frozen, denylist(), legacy, seen)
    assert reason is None
    assert candidate is not None
    assert candidate["repository"] == "github.com/owner/repo"
    assert candidate["bug_keyword"] is True
    assert candidate["changed_logical_lines"] == 2
    public = public_projection(candidate)
    assert "repository" not in public
    assert "commit" not in public
    assert "sampling_family" not in public
    assert "old_contents" not in public


def test_static_gates_reject_license_denylist_and_duplicates() -> None:
    frozen, legacy, seen = state()
    assert project_candidate(row(license="gpl-3.0"), config(), frozen, denylist(), legacy, seen)[1] == "license_not_allowlisted"
    frozen, legacy, seen = state()
    assert project_candidate(row(repos="llvm/llvm-project"), config(), frozen, denylist(), legacy, seen)[1] == "evaluation_repository_denylist"
    frozen, legacy, seen = state()
    legacy["commits"].add("a" * 40)
    assert project_candidate(row(), config(), frozen, denylist(), legacy, seen)[1] == "legacy_commit_duplicate"
    frozen, legacy, seen = state()
    first, reason = project_candidate(row(), config(), frozen, denylist(), legacy, seen)
    assert first is not None and reason is None
    assert project_candidate(row(), config(), frozen, denylist(), legacy, seen)[1] == "shard_payload_duplicate"


def test_split_assignment_is_repository_stable_and_existing_mapping_wins() -> None:
    repo = "github.com/owner/repo"
    assert assign_split(repo, {repo: "validation"}, 20260906, 10) == "validation"
    assert assign_split(repo, {}, 20260906, 10) == assign_split(repo, {}, 20260906, 10)


def test_family_retention_and_share_gate_are_deterministic() -> None:
    frozen, legacy, seen = state()
    candidates = []
    for index in range(3):
        candidate, reason = project_candidate(
            row(commit=f"{index + 1:040x}", old_contents=f"int f() {{\n int x={index};\n return x;\n}}\n"),
            config(), frozen, denylist(), legacy, seen,
        )
        assert candidate is not None and reason is None
        candidate["sampling_family"] = "shared"
        candidates.append(candidate)
    pool: dict[str, list[dict]] = {}
    for candidate in reversed(candidates):
        retain_best(pool, "shared", candidate, 2)
    assert len(pool["shared"]) == 2
    assert len({row["stable_id"] for row in pool["shared"]}) == 2
    rows = pool["shared"]
    split = rows[0]["split"]
    report = share_gate(rows, split, config())
    assert report["checks"]["samples"] is True
    assert report["checks"]["new_repositories"] is True
