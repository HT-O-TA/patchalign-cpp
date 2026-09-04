from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from scripts.training.compare_a3_confirmation import validate_config

ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    return json.loads((ROOT / "configs/evaluation/a3_confirmation_comparison_v1.json").read_text(encoding="utf-8"))


def test_confirmation_comparison_contract_is_frozen() -> None:
    value = config()
    validate_config(value)
    assert value["dataset"]["denominators"] == {"all": 124, "function": 100, "file_window": 24}
    assert value["thresholds"]["function_improvement_minimum"] == 0.02
    assert value["paired_bootstrap"]["resamples"] == 10000


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("dataset", "manifest_sha256"), "sha256:" + "0" * 64),
        (("dataset", "denominators", "function"), 99),
        (("models", "m1_r2", "adapter_sha256"), "sha256:" + "0" * 64),
        (("paired_bootstrap", "seed"), 1),
        (("thresholds", "function_improvement_minimum"), 0.0),
    ],
)
def test_confirmation_comparison_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
