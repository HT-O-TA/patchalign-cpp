from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from scripts.training.data_v2_exploratory_common import validate_config


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/training/data_v2_exploratory_replay_v0_1.json"


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_exploratory_training_contract_is_consistent() -> None:
    config = load_config()
    validate_config(config)
    assert config["scope"] == {
        "exploratory_only": True,
        "satisfies_data_v2_1_capacity_contract": False,
        "a5_dpo_started": False,
        "promotion_authorized_before_full_evaluation": False,
    }
    assert config["data"]["expected_counts"] == {"train": 780, "validation": 131}
    assert config["data"]["expected_task_levels"]["train"] == {
        "function": 416,
        "file_window": 364,
    }
    assert math.ceil(780 / config["training"]["gradient_accumulation_steps"]) == 98


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("scope", "exploratory_only"), False),
        (("scope", "promotion_authorized_before_full_evaluation"), True),
        (("training", "learning_rate"), 0.00002),
        (("training", "epochs"), 2),
        (("data", "expected_counts", "train"), 781),
        (("preregistered_evaluation", "formal_500", "minimum_pass"), 13),
    ],
)
def test_exploratory_training_rejects_protocol_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(load_config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
