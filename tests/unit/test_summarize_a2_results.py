from __future__ import annotations

import copy

import pytest

from scripts.data.summarize_a2_results import summarize


def command(status: str = "pass") -> dict[str, object]:
    return {
        "status": status,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def record(case_id: str) -> dict[str, object]:
    suites = {
        "regression": [{**command(), "matched": True}],
        "public": [{**command(), "matched": False}],
        "hidden": [{**command(), "matched": False}],
    }
    fixed_suites = copy.deepcopy(suites)
    for outcomes in fixed_suites.values():
        outcomes[0]["matched"] = True
    return {
        "schema_version": "0.2.0-draft",
        "case_id": case_id,
        "task_level": "function",
        "output_matcher": {"version": "pinned"},
        "acceptance": {
            "buggy_target_failure_observed": True,
            "fixed_all_tests_matched": True,
            "partition_contract_satisfied": True,
        },
        "versions": {
            "buggy": {"compile": command(), "suites": suites},
            "fixed": {"compile": command(), "suites": fixed_suites},
        },
    }


def test_summarize_counts_outcomes() -> None:
    result = summarize([record("one")], "sha256:" + "0" * 64)
    assert result["case_count"] == 1
    assert result["acceptance_true_counts"]["partition_contract_satisfied"] == 1
    assert result["versions"]["buggy"]["suites"]["public"] == {
        "total": 1,
        "matched": 0,
    }
    assert result["versions"]["fixed"]["suites"]["public"] == {
        "total": 1,
        "matched": 1,
    }


def test_summarize_rejects_duplicate_case_ids() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        summarize([record("one"), record("one")], "sha256:" + "0" * 64)
