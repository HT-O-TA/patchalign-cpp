from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.qualify_a3_confirmation import validate_config


ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    return json.loads((ROOT / "configs/data/a3_confirmation_qualification_v1_1.json").read_text(encoding="utf-8"))


def test_confirmation_qualification_is_bound() -> None:
    value = config()
    validate_config(value)
    assert value["required_counts"] == {"function": 100, "file_window": 24}
    assert value["qualification"]["sandbox_policy_version"] == "bubblewrap-rootless-v1"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("candidate", "manifest_sha256"), "sha256:" + "0" * 64),
        (("candidate", "source_config_sha256"), "sha256:" + "0" * 64),
        (("required_counts", "function"), 99),
        (("model", "revision"), "changed"),
        (("qualification", "double_replay_required"), False),
        (("qualification", "output_matcher_version"), "changed"),
    ],
)
def test_confirmation_qualification_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
