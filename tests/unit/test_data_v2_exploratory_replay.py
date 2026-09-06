from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from scripts.data.audit_data_v2_supply import audit
from scripts.data.build_data_v2_exploratory_replay import select_replay, stable_rank


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads(
        (ROOT / "configs/data/data_v2_exploratory_replay_v0_1.json").read_text(
            encoding="utf-8"
        )
    )


def test_contract_keeps_exploratory_boundary_explicit() -> None:
    config = load_config()
    assert config["scope"] == {
        "exploratory_only": True,
        "satisfies_data_v2_1_capacity_contract": False,
        "a5_dpo_started": False,
        "evaluation_gold_consumed": False,
        "gpu_training_allowed_only_after_passed_preflight": True,
    }
    assert config["selection"]["combined_counts"] == {"train": 780, "validation": 131}
    assert config["selection"]["combined_task_level_counts"]["train"] == {
        "function": 416,
        "file_window": 364,
    }


def test_replay_selection_is_deterministic_and_stratified() -> None:
    records = [
        {"sample_id": f"sample-{index:03d}", "task_level": level}
        for level in ("function", "file_window")
        for index in range(10)
    ]
    quotas = {"function": 4, "file_window": 3}
    first = select_replay(records, 7, quotas)
    second = select_replay(list(reversed(records)), 7, quotas)
    assert [row["sample_id"] for row in first] == [row["sample_id"] for row in second]
    assert sum(row["task_level"] == "function" for row in first) == 4
    assert sum(row["task_level"] == "file_window" for row in first) == 3
    assert stable_rank(7, "function", "sample-001") == stable_rank(7, "function", "sample-001")


def test_replay_selection_fails_closed_when_quota_is_impossible() -> None:
    with pytest.raises(RuntimeError, match="insufficient replay function"):
        select_replay([{"sample_id": "sample-001", "task_level": "function"}], 7, {"function": 2})


def test_supply_audit_sample_return_is_opt_in() -> None:
    parameter = inspect.signature(audit).parameters["include_samples"]
    assert parameter.default is False
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
