from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import pytest

from scripts.data.collect_data_v2_github_metadata import (
    evaluate_candidate,
    is_denied_repository,
    linked_issue_numbers,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_metadata_pilot_v1.json").read_text(encoding="utf-8"))


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
    assert linked_issue_numbers("Fixes #12, closes owner/repo#9 and resolves #12") == [9, 12]
    assert linked_issue_numbers("Related to #4") == []


def test_reserved_repositories_are_denied_by_exact_or_alias() -> None:
    config = load_config()
    assert is_denied_repository("github.com/llvm/llvm-project", config)
    assert is_denied_repository("github.com/someone/cppcheck", config)
    assert not is_denied_repository("github.com/good/project", config)


def test_candidate_projection_contains_no_text_patch_or_identity() -> None:
    record, reason = evaluate_candidate(detail(), license_doc(), load_config(), {"pull": "sha256:p", "license": "sha256:l"})
    assert reason == "selected"
    assert record is not None
    assert record["training_admitted"] is False
    assert record["projection"] == {
        "patch_stored": False,
        "source_code_stored": False,
        "title_or_body_stored": False,
        "user_identity_stored": False,
        "license_text_stored": False,
    }
    assert "title" not in record and "body" not in record and "patch" not in record
    assert record["explicit_linked_issue_numbers"] == [12]


def test_candidate_rejects_missing_issue_bad_license_and_large_change() -> None:
    config = load_config()
    no_issue = detail(body="Related to #12")
    assert evaluate_candidate(no_issue, license_doc(), config, {})[1] == "no_explicit_linked_issue"
    assert evaluate_candidate(detail(), license_doc("GPL-3.0"), config, {})[1] == "license_not_allowlisted"
    too_large = detail(additions=200, deletions=1)
    assert evaluate_candidate(too_large, license_doc(), config, {})[1] == "changed_lines_out_of_range"
