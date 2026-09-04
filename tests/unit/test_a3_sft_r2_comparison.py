from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from patchalign.evaluation.gates import MetricSnapshot
from scripts.training.compare_a3_sft_r2 import (
    diagnostic_comparison,
    row_timed_out,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads((ROOT / "configs/evaluation/a3_sft_r2_comparison_v1.json").read_text(encoding="utf-8"))


def test_comparison_binding_is_frozen() -> None:
    config = load_config()
    validate_config(config)
    assert config["formal_denominators"] == {"all": 500, "function": 400, "file_window": 100}
    assert config["models"]["m0"]["role"] == "promotion_baseline"
    assert config["models"]["m1"]["role"] == "diagnostic_baseline"
    assert config["models"]["m1_r2"]["role"] == "candidate"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("quality_gates", "sha256"), "sha256:" + "0" * 64),
        (("models", "m0", "role"), "candidate"),
        (("models", "m1_r2", "hashes", "scores.jsonl"), "sha256:" + "0" * 64),
        (("formal_denominators", "function"), 399),
        (("output_directory",), "/tmp/changed"),
    ],
)
def test_comparison_binding_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(load_config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)


def make_snapshot(function: tuple[bool, ...], file_window: tuple[bool, ...], timeout: float = 0.0) -> MetricSnapshot:
    return MetricSnapshot(
        function_pass_at_1=function,
        file_window_pass_at_1=file_window,
        external_pass_at_1=(),
        parse_rate=1.0,
        apply_rate=0.8,
        compile_rate=0.7,
        regression_rate=0.01,
        timeout_rate=timeout,
    )


def row(case_id: str, *, success: bool = False, timeout: bool = False, terminal: str = "public_test_failed") -> dict:
    return {
        "case_id": case_id,
        "success": success,
        "terminal_classification": terminal,
        "stages": {"public": {"outcomes": [{"timed_out": timeout}]}},
    }


def test_diagnostic_reports_transitions_without_promotion_claim() -> None:
    gates = json.loads((ROOT / "configs/evaluation/quality_gates_v1.json").read_text(encoding="utf-8"))
    before = [row("a", success=True, timeout=True), row("b")]
    after = [row("a"), row("b", success=True, timeout=True)]
    result = diagnostic_comparison(
        make_snapshot((True, False), (False,)),
        make_snapshot((False, True), (False,), timeout=0.5),
        before,
        after,
        gates,
    )
    assert result["promotion_gate"] is False
    assert result["counts"]["total_pass"] == [1, 1]
    assert result["transitions"]["success"] == {"introduced": ["b"], "resolved": ["a"], "retained": []}
    assert result["transitions"]["timeout"] == {"introduced": ["b"], "resolved": ["a"], "retained": []}


def test_timeout_detection_includes_nested_test_outcomes() -> None:
    assert row_timed_out(row("a", timeout=True)) is True
    assert row_timed_out(row("b")) is False
