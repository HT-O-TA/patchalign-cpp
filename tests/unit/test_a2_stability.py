from scripts.data.a2_stability import stable_replay


def versions(stdout_hash: str, elapsed: float = 0.1) -> dict[str, object]:
    command = {
        "status": "pass",
        "exit_code": 0,
        "elapsed_seconds": elapsed,
        "stdout_sha256": stdout_hash,
    }
    return {
        version: {
            "compile": {**command, "stdout_sha256": "compile"},
            "suites": {"all": [{**command, "test_id": 1, "matched": True}]},
        }
        for version in ("buggy", "fixed")
    }


def test_stability_ignores_elapsed_time_only() -> None:
    assert stable_replay(versions("same", 0.1), versions("same", 0.9))


def test_stability_rejects_output_hash_drift() -> None:
    assert not stable_replay(versions("first"), versions("second"))


def test_stability_rejects_incomplete_second_replay() -> None:
    first = versions("same")
    second = versions("same")
    second["buggy"]["suites"]["all"] = []  # type: ignore[index]
    assert not stable_replay(first, second)
