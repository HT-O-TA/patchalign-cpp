from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.build_a3_sft_r2_data import (
    SOURCE_FILE_SHA256,
    SOURCE_LOCK_SHA256,
    VERSION,
    safety_tags,
)
from scripts.training.a3_sft_r2_common import validate_config


ROOT = Path(__file__).resolve().parents[2]


def sample(patch: str) -> dict[str, str]:
    return {"gold_patch": patch}


def test_loop_control_and_boundary_signals_are_deterministic() -> None:
    patch = """--- a/main.cpp
+++ b/main.cpp
@@ -1 +1 @@
-for (int i = 0; i <= values.size(); ++i) {
+for (int i = 0; i < values.size(); ++i) {
"""
    assert safety_tags(sample(patch)) == [
        "loop_control_or_progress",
        "boundary_or_index_update",
    ]


def test_scale_or_allocation_signal_does_not_require_a_loop() -> None:
    patch = """--- a/main.cpp
+++ b/main.cpp
@@ -1 +1 @@
-values.resize(width);
+values.resize(width + 1);
"""
    assert safety_tags(sample(patch)) == ["scale_or_allocation_complexity"]


def test_unrelated_scalar_replacement_is_not_selected() -> None:
    patch = """--- a/main.cpp
+++ b/main.cpp
@@ -1 +1 @@
-answer = 41;
+answer = 42;
"""
    assert safety_tags(sample(patch)) == []


def test_data_and_training_contracts_are_consistent() -> None:
    data = json.loads((ROOT / "configs/data/a3_sft_r2_v1.json").read_text())
    training = json.loads(
        (ROOT / "configs/training/a3_sft_r2_v1.json").read_text()
    )
    assert data["version"] == VERSION
    assert data["source"]["formal_data_lock_sha256"] == f"sha256:{SOURCE_LOCK_SHA256}"
    assert data["source"]["file_sha256"] == {
        name: f"sha256:{digest}" for name, digest in SOURCE_FILE_SHA256.items()
    }
    assert data["selection"] == {
        "policy": "static-gold-diff-safety-v1",
        "source_dataset": "RunBugRun",
        "task_level": "function",
        "signals": [
            "loop_control_or_progress",
            "boundary_or_index_update",
            "scale_or_allocation_complexity",
        ],
        "uses_problem_statement": False,
        "uses_holdout_content": False,
        "uses_test_content": False,
        "uses_execution_feedback": False,
    }
    assert data["output"]["counts"] == training["data"]["expected_counts"]
    assert training["version"] == "a3-sft-r2-v1"
    validate_config(training)
    assert training["initialization"]["kind"] == "adapter_continuation"
    assert training["training"]["epochs"] == 1
    assert training["training"]["learning_rate"] == 0.00002
    assert training["training"]["reset_optimizer_state"] is True
    assert training["evaluation"]["scoring_protocol"] == "a3-scoring-v2"
    assert training["evaluation"]["generation"]["num_return_sequences"] == 1


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("training", "epochs"), 2),
        (("training", "learning_rate"), 0.0001),
        (("evaluation", "input_mode"), "chat_template"),
        (("evaluation", "generation", "num_return_sequences"), 2),
        (("comparison", "fixed_denominator"), 499),
    ],
)
def test_r2_config_rejects_protocol_drift(path: tuple[str, ...], value: object) -> None:
    config = json.loads((ROOT / "configs/training/a3_sft_r2_v1.json").read_text())
    changed = copy.deepcopy(config)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)


def test_r2_output_hashes_match_frozen_local_probe() -> None:
    data = json.loads((ROOT / "configs/data/a3_sft_r2_v1.json").read_text())
    assert data["output"]["counts"] == {"train": 1200, "validation": 117}
    assert data["output"]["file_sha256"] == {
        "train.jsonl": "sha256:6eeab690c134c21f6789e1a50e9581307c726acfe7d2f6b600be809221f678cc",
        "validation.jsonl": "sha256:878abb76cb73d750ac061ffff539cb5f696b000efd01bfa4b51af871a9564b73",
    }
