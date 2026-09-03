from scripts.data.qualify_a2_holdout import partition_ids, rejection_reasons


def outcome(test_id: int, matched: bool) -> dict[str, object]:
    return {"test_id": test_id, "matched": matched}


def version(items: list[dict[str, object]]) -> dict[str, object]:
    return {"compile": {"status": "pass"}, "suites": {"all": items}}


def test_partition_uses_real_buggy_and_fixed_outcomes() -> None:
    ids = list(range(10))
    buggy = version([outcome(i, i < 5) for i in ids])
    fixed = version([outcome(i, True) for i in ids])
    partitions, counts = partition_ids(ids, buggy, fixed)
    assert partitions == {
        "regression": [0, 1, 2, 3, 4],
        "public": [5],
        "hidden": [6, 7, 8, 9],
    }
    assert counts == {
        "tests": 10,
        "fixed_failures": 0,
        "target_failures": 5,
        "regression_passes": 5,
    }
    assert rejection_reasons(buggy, fixed, counts) == []


def test_partition_rejects_fixed_failure_and_insufficient_groups() -> None:
    ids = list(range(5))
    buggy = version([outcome(i, i != 4) for i in ids])
    fixed = version([outcome(i, i != 3) for i in ids])
    _, counts = partition_ids(ids, buggy, fixed)
    assert rejection_reasons(buggy, fixed, counts) == [
        "fixed_test_failed",
        "fewer_than_two_target_failures",
    ]
