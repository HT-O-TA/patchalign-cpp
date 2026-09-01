from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from patchalign.evaluation import (
    MetricSnapshot,
    evaluate_training_gate,
    load_quality_gate_config,
    paired_bootstrap_difference,
    select_pilot_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "evaluation" / "quality_gates_v1.json"


@pytest.fixture(scope="module")
def gate_config() -> dict[str, object]:
    return load_quality_gate_config(CONFIG_PATH)


def make_snapshot(*, function_improvements: int = 0) -> MetricSnapshot:
    function = tuple(index < 80 or 80 <= index < 80 + function_improvements for index in range(400))
    return MetricSnapshot(
        function_pass_at_1=function,
        file_window_pass_at_1=(True,) * 100,
        external_pass_at_1=(True,) * 150,
        parse_rate=0.95,
        apply_rate=0.90,
        compile_rate=0.85,
        regression_rate=0.02,
        timeout_rate=0.01,
    )


def test_sft_gate_passes_at_exact_two_point_primary_threshold(
    gate_config: dict[str, object],
) -> None:
    baseline = make_snapshot()
    candidate = make_snapshot(function_improvements=8)
    decision = evaluate_training_gate(
        "sft", baseline, candidate, gate_config, bootstrap_resamples=2000
    )
    assert decision["passed"] is True
    assert decision["reasons"] == []
    assert decision["paired_bootstrap_parameters"]["resamples"] == 2000
    assert decision["primary_paired_bootstrap"]["observed"] == pytest.approx(0.02)


def test_dpo_gate_passes_at_exact_one_point_primary_threshold(
    gate_config: dict[str, object],
) -> None:
    decision = evaluate_training_gate(
        "dpo",
        make_snapshot(),
        make_snapshot(function_improvements=4),
        gate_config,
        bootstrap_resamples=2000,
    )
    assert decision["passed"] is True
    assert decision["primary_paired_bootstrap"]["observed"] == pytest.approx(0.01)


def test_primary_point_improvement_below_threshold_fails(
    gate_config: dict[str, object],
) -> None:
    decision = evaluate_training_gate(
        "sft",
        make_snapshot(),
        make_snapshot(function_improvements=7),
        gate_config,
        bootstrap_resamples=1000,
    )
    assert decision["passed"] is False
    assert "primary_improvement_below_threshold" in decision["reasons"]


def test_primary_ci_with_many_paired_regressions_fails(
    gate_config: dict[str, object],
) -> None:
    baseline = replace(make_snapshot(), function_pass_at_1=(True,) * 96 + (False,) * 304)
    candidate = replace(
        make_snapshot(), function_pass_at_1=(False,) * 96 + (True,) * 104 + (False,) * 200
    )
    decision = evaluate_training_gate(
        "sft", baseline, candidate, gate_config, bootstrap_resamples=4000
    )
    assert decision["primary_paired_bootstrap"]["observed"] == pytest.approx(0.02)
    assert decision["primary_paired_bootstrap"]["lower"] < 0
    assert "primary_ci_lower_below_zero" in decision["reasons"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"parse_rate": 0.939}, "parse_rate_degradation_exceeded"),
        ({"apply_rate": 0.889}, "apply_rate_degradation_exceeded"),
        ({"compile_rate": 0.839}, "compile_rate_degradation_exceeded"),
        ({"regression_rate": 0.031}, "regression_rate_increase_exceeded"),
        ({"timeout_rate": 0.016}, "timeout_rate_increase_exceeded"),
        (
            {"file_window_pass_at_1": (False,) * 4 + (True,) * 96},
            "file_window_pass_at_1_degradation_exceeded",
        ),
        (
            {"external_pass_at_1": (False,) * 4 + (True,) * 146},
            "external_pass_at_1_degradation_exceeded",
        ),
    ),
)
def test_each_degradation_limit_is_enforced(
    gate_config: dict[str, object], changes: dict[str, object], reason: str
) -> None:
    candidate = replace(make_snapshot(function_improvements=8), **changes)
    decision = evaluate_training_gate(
        "sft", make_snapshot(), candidate, gate_config, bootstrap_resamples=1000
    )
    assert decision["passed"] is False
    assert reason in decision["reasons"]


def test_exact_degradation_boundaries_are_accepted(gate_config: dict[str, object]) -> None:
    candidate = replace(
        make_snapshot(function_improvements=8),
        parse_rate=0.94,
        apply_rate=0.89,
        compile_rate=0.84,
        regression_rate=0.03,
        timeout_rate=0.015,
        file_window_pass_at_1=(False,) * 3 + (True,) * 97,
        external_pass_at_1=(False,) * 3 + (True,) * 147,
    )
    decision = evaluate_training_gate(
        "sft", make_snapshot(), candidate, gate_config, bootstrap_resamples=2000
    )
    assert decision["passed"] is True


@pytest.mark.parametrize(
    "candidate,reason",
    (
        (
            replace(make_snapshot(function_improvements=8), function_pass_at_1=(True,) * 399),
            "function_denominator_mismatch",
        ),
        (
            replace(make_snapshot(function_improvements=8), file_window_pass_at_1=(True,) * 99),
            "file_window_denominator_mismatch",
        ),
        (
            replace(make_snapshot(function_improvements=8), external_pass_at_1=(True,) * 149),
            "external_denominator_mismatch",
        ),
    ),
)
def test_denominator_changes_are_never_silently_accepted(
    gate_config: dict[str, object], candidate: MetricSnapshot, reason: str
) -> None:
    decision = evaluate_training_gate(
        "sft", make_snapshot(), candidate, gate_config, bootstrap_resamples=500
    )
    assert decision["passed"] is False
    assert reason in decision["reasons"]


def test_leakage_or_other_validity_violation_is_an_absolute_veto(
    gate_config: dict[str, object],
) -> None:
    candidate = replace(
        make_snapshot(function_improvements=8), validity_violations=("hidden_test_leakage",)
    )
    decision = evaluate_training_gate(
        "sft", make_snapshot(), candidate, gate_config, bootstrap_resamples=500
    )
    assert decision["passed"] is False
    assert "validity_violation" in decision["reasons"]


def test_decision_and_bootstrap_are_deterministic(gate_config: dict[str, object]) -> None:
    first = evaluate_training_gate(
        "sft",
        make_snapshot(),
        make_snapshot(function_improvements=8),
        gate_config,
        bootstrap_resamples=1000,
    )
    second = evaluate_training_gate(
        "sft",
        make_snapshot(),
        make_snapshot(function_improvements=8),
        gate_config,
        bootstrap_resamples=1000,
    )
    assert first == second
    assert first["decision_sha256"] == second["decision_sha256"]


def test_paired_bootstrap_rejects_denominator_mismatch() -> None:
    with pytest.raises(ValueError, match="same non-zero denominator"):
        paired_bootstrap_difference(
            [False], [], confidence_level=0.95, resamples=100, seed=20260830
        )


def test_zero_bootstrap_resamples_are_rejected(gate_config: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="resamples must be positive"):
        evaluate_training_gate(
            "sft",
            make_snapshot(),
            make_snapshot(function_improvements=8),
            gate_config,
            bootstrap_resamples=0,
        )


def test_pilot_uses_resource_tiebreak_below_two_sample_difference(
    gate_config: dict[str, object],
) -> None:
    decision = select_pilot_candidate(
        [
            {
                "name": "bf16_lora",
                "completed": True,
                "stable": True,
                "success_count": 10,
                "peak_memory_bytes": 16_000,
                "wall_time_seconds": 100,
            },
            {
                "name": "nf4_qlora",
                "completed": True,
                "stable": True,
                "success_count": 9,
                "peak_memory_bytes": 9_000,
                "wall_time_seconds": 120,
            },
        ],
        gate_config,
    )
    assert decision["selected"] == "nf4_qlora"
    assert decision["reason"] == "quality_difference_below_two_samples_resource_tiebreak"


def test_pilot_uses_quality_at_two_sample_difference(gate_config: dict[str, object]) -> None:
    decision = select_pilot_candidate(
        [
            {
                "name": "bf16_lora",
                "completed": True,
                "stable": True,
                "success_count": 11,
                "peak_memory_bytes": 16_000,
                "wall_time_seconds": 100,
            },
            {
                "name": "nf4_qlora",
                "completed": True,
                "stable": True,
                "success_count": 9,
                "peak_memory_bytes": 9_000,
                "wall_time_seconds": 120,
            },
        ],
        gate_config,
    )
    assert decision["selected"] == "bf16_lora"
    assert decision["reason"] == "quality_difference_at_least_two_samples"


def test_pilot_rejects_more_than_two_candidates(gate_config: dict[str, object]) -> None:
    candidate = {
        "name": "candidate",
        "completed": True,
        "stable": True,
        "success_count": 1,
        "peak_memory_bytes": 1,
        "wall_time_seconds": 1,
    }
    with pytest.raises(ValueError, match="exactly two"):
        select_pilot_candidate([candidate, candidate, candidate], gate_config)
