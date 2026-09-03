from __future__ import annotations

from scripts.data.build_a1_pilot import select_isolated


def item(
    family: str,
    identifier: str,
    *,
    source: str,
    upstream_split: str = "unassigned",
) -> dict:
    record = {
        "_upstream_split": upstream_split,
        "id": identifier,
        "commit": identifier,
    }
    return {
        "record": record,
        "info": {
            "family": family,
            "level": "function",
        },
    }


def test_repository_families_are_isolated_globally_across_splits() -> None:
    pools = {
        "commitpackft": [
            item("commit-family-a", "a", source="commitpackft"),
            item("commit-family-b", "b", source="commitpackft"),
            item("commit-family-c", "c", source="commitpackft"),
        ],
        "runbugrun": [
            item("problem-shared", "r-train", source="runbugrun", upstream_split="train"),
            item("problem-shared", "r-valid", source="runbugrun", upstream_split="validation"),
            item("problem-validation", "r-valid-2", source="runbugrun", upstream_split="validation"),
        ],
    }
    wanted = {
        "train": {"commitpackft": 1, "runbugrun": 1},
        "validation": {"commitpackft": 1, "runbugrun": 1},
    }

    selected = select_isolated(pools, wanted)

    train_families = {
        record["info"]["family"] for record in selected if record["_split"] == "train"
    }
    validation_families = {
        record["info"]["family"]
        for record in selected
        if record["_split"] == "validation"
    }
    assert len(selected) == 4
    assert train_families.isdisjoint(validation_families)
    assert "problem-shared" in train_families
    assert "problem-validation" in validation_families
