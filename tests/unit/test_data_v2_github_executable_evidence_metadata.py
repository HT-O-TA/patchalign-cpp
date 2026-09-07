from __future__ import annotations

from scripts.data.collect_data_v2_github_executable_evidence_metadata import (
    project_issue_v2,
    reuse_source_issue,
)


def config() -> dict:
    return {
        "detail_gates": {
            "linked_issue_bug_label_tokens": [
                "bug",
                "bugs",
                "bugfix",
                "defect",
                "defects",
            ]
        }
    }


def test_closed_issue_without_bug_label_is_a_candidate_stratum() -> None:
    document = {
        "number": 19,
        "state": "closed",
        "labels": [{"name": "maintenance"}],
        "title": "must not be projected",
        "body": "must not be projected",
        "user": {"login": "must-not-be-projected"},
    }
    projection, reason = project_issue_v2(19, document, config())
    assert reason == "selected"
    assert projection == {
        "number": 19,
        "state": "closed",
        "bug_label_matched": False,
    }
    assert "title" not in projection
    assert "body" not in projection
    assert "user" not in projection


def test_issue_identity_and_state_remain_hard_gates() -> None:
    issue = {"number": 19, "state": "open", "labels": []}
    assert project_issue_v2(19, issue, config())[1] == "linked_issue_not_closed"
    issue["state"] = "closed"
    issue["pull_request"] = {"url": "https://api.github.com/example"}
    assert (
        project_issue_v2(19, issue, config())[1]
        == "linked_reference_is_pull_request"
    )
    issue.pop("pull_request")
    assert project_issue_v2(20, issue, config())[1] == "linked_issue_identity_mismatch"


def test_reuses_only_the_bound_no_label_rejection_as_candidate() -> None:
    checkpoint = {
        "accepted": False,
        "reason": "linked_issue_without_bug_label",
        "projection": None,
    }
    projection, reason = reuse_source_issue(checkpoint, 23)
    assert reason == "selected"
    assert projection == {
        "number": 23,
        "state": "closed",
        "bug_label_matched": False,
    }

    checkpoint["reason"] = "linked_issue_not_closed"
    assert reuse_source_issue(checkpoint, 23) == (None, "linked_issue_not_closed")


def test_reuses_accepted_labeled_issue_without_text() -> None:
    checkpoint = {
        "accepted": True,
        "reason": "selected",
        "projection": {
            "number": 29,
            "state": "closed",
            "bug_label_matched": True,
        },
    }
    projection, reason = reuse_source_issue(checkpoint, 29)
    assert reason == "selected"
    assert projection == checkpoint["projection"]
    assert projection is not checkpoint["projection"]
