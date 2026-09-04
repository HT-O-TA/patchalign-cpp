from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.training.check_a3_sft_r2_scoring import validate_config


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads(
        (ROOT / "configs/evaluation/a3_sft_r2_scoring_v1.json").read_text(
            encoding="utf-8"
        )
    )


def test_r2_scoring_binding_is_frozen() -> None:
    config = load_config()
    validate_config(config)
    assert config["holdout"]["cases"] == 500
    assert config["holdout"]["task_level_counts"] == {
        "function": 400,
        "file_window": 100,
    }
    assert config["scoring"]["protocol"] == "a3-scoring-v2"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("inference", "git_commit"), "0" * 40),
        (("inference", "adapter_sha256"), "sha256:" + "0" * 64),
        (("inference", "holdout_manifest_sha256"), "sha256:" + "0" * 64),
        (("holdout", "cases"), 499),
        (("holdout", "task_level_counts", "function"), 399),
        (("scoring", "protocol"), "strict-v1"),
        (("scoring", "config_sha256"), "sha256:" + "0" * 64),
    ],
)
def test_r2_scoring_binding_rejects_drift(
    path: tuple[str, ...], value: object
) -> None:
    changed = copy.deepcopy(load_config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
