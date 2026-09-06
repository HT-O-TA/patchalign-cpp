from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.check_data_v2_source_admission import validate_registry


ROOT = Path(__file__).resolve().parents[2]


def load_registry() -> dict:
    return json.loads(
        (ROOT / "configs/data/data_v2_source_admission_v1.json").read_text(
            encoding="utf-8"
        )
    )


def test_registry_is_closed_before_content_acquisition() -> None:
    summary = validate_registry(load_registry())
    assert summary["source_count"] == 9
    assert summary["decision_counts"] == {
        "evaluation_reserve": 4,
        "metadata_pilot": 3,
        "reject": 2,
    }
    assert summary["content_downloaded"] is False
    assert summary["training_data_frozen"] is False
    assert summary["gpu_job_authorized"] is False


def test_evaluation_reserves_are_exactly_protected() -> None:
    registry = load_registry()
    reserves = {
        source["id"]
        for source in registry["sources"]
        if source["decision"] == "evaluation_reserve"
    }
    assert reserves == set(
        registry["contamination_policy"]["protected_benchmark_source_ids"]
    )


def test_family_lower_bound_is_explicit_and_consistent() -> None:
    registry = load_registry()
    blocker = registry["family_contract_blocker"]
    assert blocker["minimum_unseen_repositories_if_repo_is_family"] == 800
    assert blocker["decision_required"] is True
    assert blocker["silent_relaxation_allowed"] is False


def test_download_or_gold_consumption_fails_closed() -> None:
    registry = load_registry()
    changed = copy.deepcopy(registry)
    changed["state"]["content_downloaded"] = True
    with pytest.raises(RuntimeError, match="content_downloaded"):
        validate_registry(changed)

    changed = copy.deepcopy(registry)
    changed["contamination_policy"]["evaluation_gold_consumed"] = True
    with pytest.raises(RuntimeError, match="evaluation gold"):
        validate_registry(changed)


def test_rejected_source_cannot_schedule_followup() -> None:
    registry = load_registry()
    changed = copy.deepcopy(registry)
    rejected = next(
        source for source in changed["sources"] if source["decision"] == "reject"
    )
    rejected["next_action"] = "download"
    with pytest.raises(RuntimeError, match="rejected source has action"):
        validate_registry(changed)
