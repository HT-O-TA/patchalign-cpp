from __future__ import annotations

from scripts.evaluation.aggregate_a5_dpo_final import cpp_counts, external_counts, transitions


def cpp_row(case_id: str, terminal: str, *, success: bool = False, timeout: bool = False) -> dict:
    passed = terminal == "success"
    return {
        "case_id": case_id,
        "terminal_classification": terminal,
        "success": success,
        "stages": {
            "parse": {"status": "passed"},
            "apply": {"status": "passed"},
            "build": {"status": "passed"},
            "public": {"status": "passed"},
            "hidden": {"status": "passed" if terminal in {"success", "regression_failed"} else "failed", "timed_out": timeout},
            "regression": {"status": "passed" if passed else "not_run"},
        },
    }


def test_cpp_counts_keep_hidden_and_regression_separate() -> None:
    counts = cpp_counts([
        cpp_row("a", "success", success=True),
        cpp_row("b", "regression_failed"),
        cpp_row("c", "hidden_test_failed", timeout=True),
    ])
    assert counts == {
        "total": 3,
        "parse_success": 3,
        "apply_success": 3,
        "compile_success": 3,
        "public_test_success": 3,
        "hidden_test_success": 2,
        "pass_at_1": 1,
        "regression_failures": 1,
        "timeouts": 1,
    }


def test_external_counts_follow_rootfs_apply_and_terminal_build() -> None:
    rows = [
        {"terminal_classification": "success", "success": True, "timed_out": False, "rootfs_result": {"stages": {"apply": {"returncode": 0}}}},
        {"terminal_classification": "build_failed", "success": False, "timed_out": False, "rootfs_result": {"stages": {"apply": {"returncode": 0}}}},
        {"terminal_classification": "parse_failed", "success": False, "timed_out": False, "rootfs_result": None},
    ]
    assert external_counts(rows) == {
        "total": 3,
        "parse_success": 2,
        "apply_success": 2,
        "compile_success": 1,
        "pass_at_1": 1,
        "timeouts": 0,
    }


def test_transitions_are_paired_and_directional() -> None:
    before = [cpp_row("a", "success", success=True), cpp_row("b", "hidden_test_failed"), cpp_row("c", "success", success=True)]
    after = [cpp_row("a", "hidden_test_failed"), cpp_row("b", "success", success=True), cpp_row("c", "success", success=True)]
    result = transitions(before, after)
    assert result["introduced_failures"] == ["a"]
    assert result["resolved_failures"] == ["b"]
    assert result["retained_successes"] == ["c"]
