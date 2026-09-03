from scripts.data.qualify_a2_holdout import rejection_reasons


def test_qualification_rejects_incomplete_timeout_replay() -> None:
    version = {"compile": {"status": "pass"}}
    counts = {
        "tests": 100,
        "fixed_failures": 100,
        "target_failures": 0,
        "regression_passes": 0,
    }
    reasons = rejection_reasons(
        version, version, counts, execution_complete=False
    )
    assert reasons[0] == "test_execution_incomplete"
