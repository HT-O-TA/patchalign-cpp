from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

from scripts.data.collect_data_v2_github_detail_pilot import (
    project_issue,
    project_license,
    checkpointed_request,
    project_pr_detail,
    select_fixed_candidates,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


def denylist() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_evaluation_denylist_v1.json").read_text(encoding="utf-8"))


def test_static_config_freezes_inputs_scope_and_request_budget() -> None:
    frozen = json.loads((ROOT / "configs/data/data_v2_github_detail_pilot_v1.json").read_text(encoding="utf-8"))
    validate_config(frozen)
    assert frozen["discovery"]["slurm_job_id"] == 96939
    assert frozen["discovery"]["candidates"]["count"] == 7721
    assert frozen["api"]["maximum_logical_requests"] == 600
    assert frozen["scope"]["patch_or_source_requested"] is False
    assert frozen["scope"]["training_admitted"] is False


def config() -> dict:
    return {
        "sampling": {
            "seed": 20260907,
            "targets": {"train": 160, "validation": 40},
            "minimum_repository_coverage": {"train": 100, "validation": 20},
            "maximum_candidates_per_repository": 2,
        },
        "detail_gates": {
            "changed_files": {"minimum": 1, "maximum": 10},
            "changed_lines": {"minimum": 2, "maximum": 200},
            "require_bug_label": True,
            "linked_issue_bug_label_tokens": ["bug", "bugs", "bugfix", "defect", "defects"],
            "allowed_spdx": ["MIT", "Apache-2.0"],
        },
    }


def candidate(split: str, repository_index: int, number: int) -> dict:
    repository = f"github.com/{split}/repo-{repository_index:03d}"
    candidate_id = "ghpr-" + hashlib.sha256(f"{repository}\0{number}".encode("utf-8")).hexdigest()[:24]
    return {
        "candidate_id": candidate_id,
        "source_dataset": "github-linked-pr-discovery-v2.1",
        "repository_split_group": repository,
        "projected_split": split,
        "pr_number": number,
        "pr_api_url": f"https://api.github.com/repos/{split}/repo-{repository_index:03d}/pulls/{number}",
    }


def detail(**updates: object) -> dict:
    value = {
        "number": 7,
        "body": "Fixes #9",
        "created_at": "2025-01-01T00:00:00Z",
        "merged_at": "2025-01-02T00:00:00Z",
        "merge_commit_sha": "a" * 40,
        "changed_files": 2,
        "additions": 10,
        "deletions": 3,
        "base": {
            "sha": "b" * 40,
            "repo": {
                "full_name": "Fresh/Project",
                "fork": False,
                "archived": False,
                "language": "C++",
            },
        },
        "head": {"sha": "c" * 40},
        "title": "must not be projected",
        "user": {"login": "must-not-be-projected"},
    }
    value.update(updates)
    return value


def test_fixed_selection_is_deterministic_round_robin_and_diverse() -> None:
    rows = []
    for split, repositories in (("train", 120), ("validation", 25)):
        for repository_index in range(repositories):
            rows.extend(candidate(split, repository_index, number) for number in (1, 2, 3))
    first = select_fixed_candidates(rows, config(), denylist())
    second = select_fixed_candidates(list(reversed(rows)), config(), denylist())
    assert first == second
    assert sum(row["projected_split"] == "train" for row in first) == 160
    assert sum(row["projected_split"] == "validation" for row in first) == 40
    assert len({row["repository_split_group"] for row in first if row["projected_split"] == "train"}) == 120
    assert len({row["repository_split_group"] for row in first if row["projected_split"] == "validation"}) == 25
    per_repo: dict[str, int] = {}
    for row in first:
        per_repo[row["repository_split_group"]] = per_repo.get(row["repository_split_group"], 0) + 1
    assert max(per_repo.values()) == 2


def test_pr_projection_accepts_github_casefold_and_drops_text_and_user() -> None:
    row = {
        "candidate_id": "ghpr-x",
        "repository_split_group": "github.com/fresh/project",
        "pr_number": 7,
    }
    projected, reason = project_pr_detail(row, detail(), config(), denylist())
    assert reason == "selected"
    assert projected is not None
    assert projected["repository_split_group"] == "github.com/fresh/project"
    assert projected["repository_full_name"] == "Fresh/Project"
    assert projected["linked_issue_number"] == 9
    serialized = json.dumps(projected)
    assert "must not be projected" not in serialized
    assert "title" not in projected and "body" not in projected and "user" not in projected


def test_pr_projection_rejects_large_change_and_denied_repository() -> None:
    row = {"candidate_id": "ghpr-x", "repository_split_group": "github.com/fresh/project", "pr_number": 7}
    too_large = detail(additions=198, deletions=3)
    assert project_pr_detail(row, too_large, config(), denylist())[1] == "changed_lines_out_of_range"
    denied_row = {"candidate_id": "ghpr-y", "repository_split_group": "github.com/llvm/llvm-project", "pr_number": 7}
    denied_detail = detail()
    denied_detail["base"] = copy.deepcopy(denied_detail["base"])
    denied_detail["base"]["repo"] = copy.deepcopy(denied_detail["base"]["repo"])
    denied_detail["base"]["repo"]["full_name"] = "llvm/llvm-project"
    assert project_pr_detail(denied_row, denied_detail, config(), denylist())[1] == "exact_protected_repository"


def test_issue_and_license_projection_keep_only_audit_fields() -> None:
    issue = {
        "number": 9,
        "state": "closed",
        "labels": [{"name": "type: bug"}],
        "title": "must not be stored",
        "body": "must not be stored",
        "user": {"login": "must-not-be-stored"},
    }
    projected_issue, reason = project_issue(9, issue, config())
    assert reason == "selected"
    assert projected_issue == {"number": 9, "state": "closed", "bug_label_matched": True}
    license_document = {
        "path": "LICENSE",
        "license": {"spdx_id": "MIT", "key": "mit"},
        "content": base64.b64encode(b"license text").decode("ascii"),
    }
    projected_license, reason = project_license(license_document, config())
    assert reason == "selected"
    assert projected_license is not None
    assert "content" not in projected_license
    assert projected_license["content_sha256"].startswith("sha256:")


def test_checkpointed_request_persists_expected_not_found_without_projection(tmp_path: Path) -> None:
    class MissingClient:
        def get(self, url: str) -> tuple[dict, dict]:
            return {}, {"url": url, "sha256": "sha256:" + "0" * 64, "http_status": 404, "rate_limit": {}}

    projected = False

    def projector(document: dict) -> tuple[dict | None, str]:
        nonlocal projected
        projected = True
        return {"unexpected": True}, "selected"

    path = tmp_path / "missing.json"
    result, cached = checkpointed_request(
        path,
        common={"candidate_id": "ghpr-" + "a" * 24, "stage": "license"},
        url="https://api.github.com/repos/example/project/license",
        client=MissingClient(),
        projector=projector,
    )
    assert cached is False
    assert projected is False
    assert result["accepted"] is False
    assert result["reason"] == "http_404"
    assert path.is_file()
