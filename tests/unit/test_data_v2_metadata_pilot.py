from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import pytest

from scripts.data.collect_data_v2_github_metadata import (
    collect,
    evaluate_candidate,
    is_denied_repository,
    linked_issue_numbers,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_metadata_pilot_v1_1.json").read_text(encoding="utf-8"))


def detail(**updates: object) -> dict:
    value = {
        "number": 17,
        "html_url": "https://github.com/good/project/pull/17",
        "title": "Fix boundary condition",
        "body": "Fixes #12",
        "created_at": "2023-02-01T00:00:00Z",
        "merged_at": "2023-02-02T00:00:00Z",
        "merge_commit_sha": "a" * 40,
        "changed_files": 2,
        "additions": 10,
        "deletions": 4,
        "labels": [{"name": "bug"}],
        "base": {
            "sha": "b" * 40,
            "repo": {
                "full_name": "good/project",
                "html_url": "https://github.com/good/project",
                "language": "C++",
                "stargazers_count": 500,
                "fork": False,
                "archived": False,
            },
        },
        "head": {"sha": "c" * 40},
    }
    value.update(updates)
    return value


def issue_doc(*, labels: list[str] | None = None) -> dict:
    return {
        "number": 12,
        "html_url": "https://github.com/good/project/issues/12",
        "state": "closed",
        "title": "Boundary defect",
        "body": "The final element is skipped",
        "labels": [{"name": name} for name in (labels or ["type: bug"])],
    }


def license_doc(spdx: str = "MIT") -> dict:
    return {
        "path": "LICENSE",
        "html_url": "https://github.com/good/project/blob/main/LICENSE",
        "content": base64.b64encode(b"MIT license text").decode("ascii"),
        "license": {"key": spdx.lower(), "spdx_id": spdx},
    }


def test_config_forbids_content_and_training_admission() -> None:
    validate_config(load_config())
    changed = copy.deepcopy(load_config())
    changed["projection"]["store_patch"] = True
    with pytest.raises(RuntimeError, match="forbidden projection"):
        validate_config(changed)


def test_issue_link_parser_is_explicit_and_deduplicated() -> None:
    assert linked_issue_numbers("Fixes #12, closes other/repo#9 and resolves #12", "good/project") == [12]
    assert linked_issue_numbers("Related to #4") == []


def test_reserved_repositories_are_denied_by_exact_or_alias() -> None:
    config = load_config()
    assert is_denied_repository("github.com/llvm/llvm-project", config)
    assert is_denied_repository("github.com/someone/cppcheck", config)
    assert not is_denied_repository("github.com/good/project", config)


def test_candidate_projection_contains_no_text_patch_or_identity() -> None:
    record, reason = evaluate_candidate(detail(), issue_doc(), license_doc(), load_config(), {"pull": "sha256:p", "linked_issue": "sha256:i", "license": "sha256:l"})
    assert reason == "selected"
    assert record is not None
    assert record["training_admitted"] is False
    assert record["projection"] == {
        "patch_stored": False,
        "source_code_stored": False,
        "title_or_body_stored": False,
        "user_identity_stored": False,
        "license_text_stored": False,
        "linked_issue_title_or_body_stored": False,
    }
    assert "title" not in record and "body" not in record and "patch" not in record
    assert record["explicit_linked_issue_numbers"] == [12]


def test_candidate_rejects_missing_issue_bad_license_and_large_change() -> None:
    config = load_config()
    no_issue = detail(body="Related to #12")
    assert evaluate_candidate(no_issue, issue_doc(), license_doc(), config, {})[1] == "no_explicit_same_repository_linked_issue"
    assert evaluate_candidate(detail(), issue_doc(), license_doc("GPL-3.0"), config, {})[1] == "license_not_allowlisted"
    too_large = detail(additions=200, deletions=1)
    assert evaluate_candidate(too_large, issue_doc(), license_doc(), config, {})[1] == "changed_lines_out_of_range"
    assert evaluate_candidate(detail(), issue_doc(labels=["enhancement"]), license_doc(), config, {})[1] == "linked_issue_without_bug_label"

def test_collect_fetches_issue_before_license_and_projects_one_record(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config()

    class FakeClient:
        authenticated = False
        last_rate = {"X-RateLimit-Remaining": "57"}

        def __init__(self) -> None:
            self.response_hashes: list[dict] = []
            self.urls: list[str] = []

        def get(self, url: str) -> dict:
            self.urls.append(url)
            self.response_hashes.append({"url": url, "sha256": f"sha256:{len(self.urls)}", "etag": ""})
            if url.startswith("/search/issues?"):
                return {"total_count": 1, "incomplete_results": False, "items": [{"pull_request": {"url": "https://api.github.com/repos/good/project/pulls/17"}}]}
            if url.endswith("/pulls/17"):
                return detail()
            if url.endswith("/issues/12"):
                return issue_doc()
            if url.endswith("/license"):
                return license_doc()
            raise AssertionError(url)

    monkeypatch.setenv("PATCHALIGN_GIT_COMMIT", "d" * 40)
    client = FakeClient()
    records, summary, manifest = collect(config, client)  # type: ignore[arg-type]
    assert len(records) == 1
    assert summary["selected_unique_repositories"] == 1
    assert summary["training_admitted"] is False
    assert client.urls[1:] == [
        "https://api.github.com/repos/good/project/pulls/17",
        "/repos/good/project/issues/12",
        "/repos/good/project/license",
    ]
    assert manifest["content_boundaries"]["patch_requested_or_stored"] is False
