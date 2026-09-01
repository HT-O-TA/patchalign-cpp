"""Deterministic patch evaluation primitives."""

from .gates import (
    MetricSnapshot,
    evaluate_training_gate,
    load_quality_gate_config,
    paired_bootstrap_difference,
    select_pilot_candidate,
)
from .scorer import score_prediction, summarize_scores

__all__ = [
    "MetricSnapshot",
    "evaluate_training_gate",
    "load_quality_gate_config",
    "paired_bootstrap_difference",
    "score_prediction",
    "select_pilot_candidate",
    "summarize_scores",
]
