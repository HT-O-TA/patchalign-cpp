from scripts.data.check_a2_replay_stability import load
from scripts.data.a2_stability import stable_replay


def command(stdout_hash: str, elapsed: float) -> dict[str, object]:
    return {
        "status": "pass",
        "exit_code": 0,
        "elapsed_seconds": elapsed,
        "stdout_sha256": stdout_hash,
    }


def versions(suite: str, elapsed: float = 0.1) -> dict[str, object]:
    return {
        version: {
            "compile": command("compile", elapsed),
            "suites": {
                suite: [
                    {**command("one", elapsed), "test_id": 2, "matched": True},
                    {**command("two", elapsed), "test_id": 1, "matched": False},
                ]
            },
        }
        for version in ("buggy", "fixed")
    }


def test_stability_ignores_suite_labels_order_and_elapsed() -> None:
    first = versions("all", 0.1)
    second = versions("hidden", 0.9)
    for result in second.values():
        result["suites"]["hidden"].reverse()  # type: ignore[index]
    assert stable_replay(first, second)


def test_load_rejects_duplicate_case_ids(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    path.write_text('{"case_id":"one"}\n{"case_id":"one"}\n')
    try:
        load(path)
    except RuntimeError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate case_id was accepted")
