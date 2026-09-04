from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.training.a3_sft_r2_inference_common import validate_config


ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    return json.loads((ROOT / "configs/evaluation/a3_confirmation_inference_v1.json").read_text(encoding="utf-8"))


def test_confirmation_inference_is_frozen_before_generation() -> None:
    value = config()
    validate_config(value)
    evaluation = value["evaluation"]
    assert evaluation["required_task_levels"] == {"function": 100, "file_window": 24}
    assert evaluation["holdout_manifest_sha256"] == "sha256:7adf960fff4e7f1ee3ca95539ffa1196c3421805659c94bb46a29d0022690917"
    assert evaluation["prompt_artifact_sha256"] == "sha256:cf141a9d4f90c8fd9f1a8f9cd03509cc2b2fd48905a3c1e533e93cad702ad58f"
    assert evaluation["generation"]["do_sample"] is False


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("run_id",), "changed"),
        (("evaluation", "holdout_manifest_sha256"), "sha256:" + "0" * 64),
        (("evaluation", "prompt_artifact_sha256"), "sha256:" + "0" * 64),
        (("evaluation", "required_task_levels", "file_window"), 25),
        (("evaluation", "generation", "do_sample"), True),
    ],
)
def test_confirmation_inference_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
