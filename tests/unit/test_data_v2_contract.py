from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.check_data_v2_contract import (
    assign_new_split,
    canonical_repository,
    repository_sampling_family,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[2]


def load_contract() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_contract_v2_1.json").read_text(encoding="utf-8"))


def test_accepted_contract_keeps_training_and_gpu_closed() -> None:
    result = validate_contract(load_contract())
    assert result["owner_accepted"] is True
    assert result["repository_caps"] == {"train": 40, "validation": 20}
    assert result["source_content_download_authorized"] is False
    assert result["gpu_authorized"] is False


def test_repository_identity_is_canonical_across_urls() -> None:
    expected = "github.com/owner/repo"
    assert canonical_repository("https://GitHub.com/Owner/Repo.git") == expected
    assert canonical_repository("git@github.com:OWNER/REPO.git") == expected


def test_split_assignment_is_deterministic() -> None:
    first = assign_new_split("github.com/owner/repo", 10, 20260906)
    second = assign_new_split("github.com/owner/repo", 10, 20260906)
    assert first == second
    assert first in {"train", "validation"}


def test_sampling_family_uses_symbol_or_stable_fallback() -> None:
    group = "github.com/owner/repo"
    assert repository_sampling_family(group, "Src/Foo.cpp", "issue-17") == "github.com/owner/repo|src/foo.cpp|issue-17"
    anchor = "sha256:" + "a" * 64
    assert repository_sampling_family(group, "src/foo.cpp", hunk_anchor_hash=anchor).endswith(anchor)
    with pytest.raises(RuntimeError, match="fallback"):
        repository_sampling_family(group, "src/foo.cpp")


def test_contract_rejects_split_or_sampling_relaxation() -> None:
    changed = copy.deepcopy(load_contract())
    changed["split"]["benchmark_repository_split_group_overlap"] = 1
    with pytest.raises(RuntimeError, match="benchmark overlap"):
        validate_contract(changed)

    changed = copy.deepcopy(load_contract())
    changed["caps"]["maximum_samples_per_sampling_family_across_v1_plus_increment"] = 3
    with pytest.raises(RuntimeError, match="sampling-family cap"):
        validate_contract(changed)
