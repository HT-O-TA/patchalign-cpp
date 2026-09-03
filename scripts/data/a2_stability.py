"""Determinism projection for repeated A2 qualification replays."""

from __future__ import annotations

from typing import Any


def _without_elapsed(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "elapsed_seconds"}


def execution_projection(versions: dict[str, Any]) -> dict[str, Any]:
    projection = {}
    for version in ("buggy", "fixed"):
        result = versions[version]
        projection[version] = {
            "compile": _without_elapsed(result["compile"]),
            "tests": [
                _without_elapsed(outcome)
                for outcome in result.get("suites", {}).get("all", [])
            ],
        }
    return projection


def stable_replay(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Ignore timing only; require identical statuses, stream hashes and matches."""

    return execution_projection(first) == execution_projection(second)
