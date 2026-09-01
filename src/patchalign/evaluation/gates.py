"""Deterministic pre-registered quality gates for SFT, DPO, and pilot selection."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Literal, Sequence


TrainingStage = Literal["sft", "dpo"]


@dataclass(frozen=True)
class MetricSnapshot:
    """Metrics for one model on the same ordered, frozen evaluation samples."""

    function_pass_at_1: tuple[bool, ...]
    file_window_pass_at_1: tuple[bool, ...]
    external_pass_at_1: tuple[bool, ...]
    parse_rate: float
    apply_rate: float
    compile_rate: float
    regression_rate: float
    timeout_rate: float
    validity_violations: tuple[str, ...] = ()


def load_quality_gate_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("version") != "1.0.0":
        raise ValueError("unsupported quality-gate config version")
    return config


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rate(outcomes: Sequence[bool]) -> float:
    if not outcomes:
        raise ValueError("metric outcome sequence must not be empty")
    return sum(outcomes) / len(outcomes)


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("cannot take a quantile of an empty sequence")
    position = probability * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def paired_bootstrap_difference(
    baseline: Sequence[bool],
    candidate: Sequence[bool],
    *,
    confidence_level: float,
    resamples: int,
    seed: int,
) -> dict[str, float]:
    """Return a deterministic paired-bootstrap interval for candidate minus baseline."""

    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("paired outcomes must have the same non-zero denominator")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between zero and one")
    if resamples < 1:
        raise ValueError("resamples must be positive")

    differences = [int(new) - int(old) for old, new in zip(baseline, candidate, strict=True)]
    random_generator = random.Random(seed)
    sample_size = len(differences)
    bootstrap_deltas = sorted(
        sum(differences[random_generator.randrange(sample_size)] for _ in range(sample_size))
        / sample_size
        for _ in range(resamples)
    )
    tail = (1.0 - confidence_level) / 2.0
    return {
        "observed": sum(differences) / sample_size,
        "lower": _quantile(bootstrap_deltas, tail),
        "upper": _quantile(bootstrap_deltas, 1.0 - tail),
    }


def _validate_rate(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a finite rate between zero and one")


def evaluate_training_gate(
    stage: TrainingStage,
    baseline: MetricSnapshot,
    candidate: MetricSnapshot,
    config: dict[str, Any],
    *,
    bootstrap_resamples: int | None = None,
) -> dict[str, Any]:
    """Evaluate all frozen improvement, degradation, validity, and denominator gates."""

    if stage not in {"sft", "dpo"}:
        raise ValueError("stage must be sft or dpo")
    for snapshot in (baseline, candidate):
        for rate_name in ("parse_rate", "apply_rate", "compile_rate", "regression_rate", "timeout_rate"):
            _validate_rate(rate_name, getattr(snapshot, rate_name))

    slices = config["formal_slices"]
    reasons: list[str] = []
    denominators = {
        "function": [len(baseline.function_pass_at_1), len(candidate.function_pass_at_1)],
        "file_window": [len(baseline.file_window_pass_at_1), len(candidate.file_window_pass_at_1)],
        "external": [len(baseline.external_pass_at_1), len(candidate.external_pass_at_1)],
    }
    if denominators["function"] != [slices["function_count"], slices["function_count"]]:
        reasons.append("function_denominator_mismatch")
    if denominators["file_window"] != [slices["file_window_count"], slices["file_window_count"]]:
        reasons.append("file_window_denominator_mismatch")
    if (
        denominators["external"][0] != denominators["external"][1]
        or denominators["external"][0] < slices["external_min_count"]
    ):
        reasons.append("external_denominator_mismatch")
    if baseline.validity_violations or candidate.validity_violations:
        reasons.append("validity_violation")

    bootstrap = config["paired_bootstrap"]
    primary_ci: dict[str, float] | None = None
    if denominators["function"][0] == denominators["function"][1] and denominators["function"][0] > 0:
        primary_ci = paired_bootstrap_difference(
            baseline.function_pass_at_1,
            candidate.function_pass_at_1,
            confidence_level=bootstrap["confidence_level"],
            resamples=bootstrap_resamples or bootstrap["resamples"],
            seed=bootstrap["seed"],
        )
    else:
        reasons.append("primary_ci_unavailable")

    primary_threshold = config["primary_improvement"][f"{stage}_absolute"]
    ci_lower_minimum = config["primary_improvement"]["ci_lower_minimum"]
    if primary_ci is not None:
        if primary_ci["observed"] + 1e-12 < primary_threshold:
            reasons.append("primary_improvement_below_threshold")
        if primary_ci["lower"] + 1e-12 < ci_lower_minimum:
            reasons.append("primary_ci_lower_below_zero")

    maximum = config["maximum_degradation"]
    deltas = {
        "parse_rate": candidate.parse_rate - baseline.parse_rate,
        "apply_rate": candidate.apply_rate - baseline.apply_rate,
        "compile_rate": candidate.compile_rate - baseline.compile_rate,
        "regression_rate": candidate.regression_rate - baseline.regression_rate,
        "timeout_rate": candidate.timeout_rate - baseline.timeout_rate,
        "file_window_pass_at_1": None,
        "external_pass_at_1": None,
    }
    for name in ("parse_rate", "apply_rate", "compile_rate"):
        if deltas[name] is not None and deltas[name] + 1e-12 < -maximum[name]:
            reasons.append(f"{name}_degradation_exceeded")
    for name, config_name in (
        ("regression_rate", "regression_rate_increase"),
        ("timeout_rate", "timeout_rate_increase"),
    ):
        if deltas[name] is not None and deltas[name] - 1e-12 > maximum[config_name]:
            reasons.append(f"{name}_increase_exceeded")

    if denominators["file_window"][0] == denominators["file_window"][1] and denominators["file_window"][0] > 0:
        deltas["file_window_pass_at_1"] = _rate(candidate.file_window_pass_at_1) - _rate(
            baseline.file_window_pass_at_1
        )
        if deltas["file_window_pass_at_1"] + 1e-12 < -maximum["file_window_pass_at_1"]:
            reasons.append("file_window_pass_at_1_degradation_exceeded")
    if denominators["external"][0] == denominators["external"][1] and denominators["external"][0] > 0:
        deltas["external_pass_at_1"] = _rate(candidate.external_pass_at_1) - _rate(
            baseline.external_pass_at_1
        )
        if deltas["external_pass_at_1"] + 1e-12 < -maximum["external_pass_at_1"]:
            reasons.append("external_pass_at_1_degradation_exceeded")

    unique_reasons = sorted(set(reasons))
    decision: dict[str, Any] = {
        "gate_version": config["version"],
        "stage": stage,
        "passed": not unique_reasons,
        "reasons": unique_reasons,
        "denominators": denominators,
        "primary_threshold": primary_threshold,
        "primary_paired_bootstrap": primary_ci,
        "deltas": deltas,
        "config_sha256": _canonical_sha256(config),
    }
    decision["decision_sha256"] = _canonical_sha256(decision)
    return decision


def select_pilot_candidate(candidates: Sequence[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Select a stable pilot winner, using quality only for a difference of at least two successes."""

    eligible = [candidate for candidate in candidates if candidate["completed"] and candidate["stable"]]
    if not eligible:
        raise ValueError("pilot has no completed and stable candidate")
    minimum_difference = config["pilot"]["minimum_success_count_difference"]
    highest_successes = max(candidate["success_count"] for candidate in eligible)
    lowest_successes = min(candidate["success_count"] for candidate in eligible)
    if highest_successes - lowest_successes >= minimum_difference:
        winner = min(
            (candidate for candidate in eligible if candidate["success_count"] == highest_successes),
            key=lambda candidate: (candidate["peak_memory_bytes"], candidate["wall_time_seconds"], candidate["name"]),
        )
        reason = "quality_difference_at_least_two_samples"
    else:
        winner = min(
            eligible,
            key=lambda candidate: (candidate["peak_memory_bytes"], candidate["wall_time_seconds"], candidate["name"]),
        )
        reason = "quality_difference_below_two_samples_resource_tiebreak"
    decision = {
        "gate_version": config["version"],
        "selected": winner["name"],
        "reason": reason,
        "eligible_names": sorted(candidate["name"] for candidate in eligible),
    }
    decision["decision_sha256"] = _canonical_sha256(decision)
    return decision
