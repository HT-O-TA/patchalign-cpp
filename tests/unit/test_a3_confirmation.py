from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.build_a3_confirmation import validate_config


ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    return json.loads((ROOT / "configs/data/a3_confirmation_v1.json").read_text(encoding="utf-8"))


def test_confirmation_contract_is_frozen_before_evaluation() -> None:
    value = config()
    validate_config(value)
    assert value["candidate_counts"] == {"function": 218, "file_window": 53}
    assert value["required_counts"] == {"function": 100, "file_window": 25}
    assert value["qualification"]["double_replay_required"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("seed",), 1),
        (("candidate_counts", "function"), 217),
        (("required_counts", "file_window"), 24),
        (("qualification", "max_input_tokens"), 8192),
        (("qualification", "double_replay_required"), False),
    ],
)
def test_confirmation_contract_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
