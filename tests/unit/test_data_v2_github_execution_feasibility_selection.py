from __future__ import annotations

import hashlib

from scripts.data.build_data_v2_github_execution_feasibility_selection import (
    label_stratum,
    select_fixed,
)


def config() -> dict:
    return {
        "source_metadata": {"candidates": {"count": 104}},
        "selection": {
            "seed": 20260908,
            "split_stratum_targets": {
                "train": {"bug_label": 8, "no_bug_label": 8},
                "validation": {"bug_label": 2, "no_bug_label": 2},
            },
            "split_order": ["train", "validation"],
            "stratum_order": ["bug_label", "no_bug_label"],
        },
    }


def row(index: int, split: str, labeled: bool, repository: str | None = None) -> dict:
    candidate_id = "ghpr-" + hashlib.sha256(str(index).encode()).hexdigest()[:24]
    return {
        "candidate_id": candidate_id,
        "projected_split": split,
        "repository_split_group": repository or f"github.com/{split}/repo-{index:03d}",
        "linked_issue": {"bug_label_matched": labeled},
    }


def source_rows() -> list[dict]:
    rows = []
    for index in range(50):
        rows.append(row(index, "train", index % 2 == 0))
    for index in range(50, 104):
        rows.append(row(index, "validation", index % 2 == 0))
    return rows


def test_label_stratum_is_explicit() -> None:
    assert label_stratum(row(1, "train", True)) == "bug_label"
    assert label_stratum(row(2, "train", False)) == "no_bug_label"


def test_selection_is_deterministic_balanced_and_repository_unique() -> None:
    rows = source_rows()
    first = select_fixed(rows, config())
    second = select_fixed(list(reversed(rows)), config())
    assert first == second
    assert len(first) == 20
    assert [item["feasibility_order"] for item in first] == list(range(20))
    assert len({item["repository_split_group"] for item in first}) == 20
    counts = {}
    for item in first:
        key = (item["projected_split"], item["selection_stratum"])
        counts[key] = counts.get(key, 0) + 1
        assert item["replacement_allowed"] is False
    assert counts == {
        ("train", "bug_label"): 8,
        ("train", "no_bug_label"): 8,
        ("validation", "bug_label"): 2,
        ("validation", "no_bug_label"): 2,
    }


def test_selection_skips_repository_collision_between_strata() -> None:
    rows = source_rows()
    shared = "github.com/train/shared"
    rows[0]["repository_split_group"] = shared
    rows[1]["repository_split_group"] = shared
    selected = select_fixed(rows, config())
    repositories = [item["repository_split_group"] for item in selected]
    assert len(repositories) == len(set(repositories))
