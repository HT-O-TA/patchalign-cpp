from __future__ import annotations

from collections import Counter

import pytest

from scripts.diagnostics.analyze_generalization_failure import (
    bin_label,
    classify_edit,
    diff_changed_lines,
    ks_distance,
    terminal_summary,
    total_variation,
    verify_model_identity,
)


def test_changed_line_and_edit_type_reuse_frozen_convention() -> None:
    old = "int main() {\n  return 1;\n}\n"
    new = "int main() {\n  return 2;\n}\n"
    changed = diff_changed_lines(old, new, "main.cpp")
    assert changed == 1
    assert classify_edit(old, new, changed) == "single_line"


def test_added_called_function_precedes_line_count_classification() -> None:
    old = "int main() {\n  return 1;\n}\n"
    new = "int helper() { return 2; }\nint main() {\n  return helper();\n}\n"
    assert classify_edit(old, new, diff_changed_lines(old, new, "main.cpp")) == "add_helper"


def test_distribution_metrics_and_bins_are_exact() -> None:
    assert total_variation(Counter({"a": 2}), Counter({"a": 1, "b": 1})) == 0.5
    assert ks_distance([1, 2], [2, 3]) == 0.5
    assert bin_label(50, [0, 50, 100]) == "[50,100)"
    with pytest.raises(RuntimeError, match="outside configured bins"):
        bin_label(100, [0, 50, 100])


def test_internal_terminal_funnel_is_monotonic_and_requires_full_pass() -> None:
    rows = [
        {"terminal_classification": "apply_failed"},
        {"terminal_classification": "hidden_test_failed"},
        {"terminal_classification": "regression_failed"},
        {"terminal_classification": "success"},
    ]
    result = terminal_summary(rows)
    assert result["funnel_counts"] == {
        "parse": 4,
        "policy": 4,
        "apply": 3,
        "build": 3,
        "public": 3,
        "hidden": 2,
        "regression": 1,
    }


def test_model_identity_requires_adapter_and_artifact_bindings(tmp_path) -> None:
    import json

    run = tmp_path / "run.json"
    score = tmp_path / "score.json"
    adapter, prediction, execution = "a" * 64, "b" * 64, "c" * 64
    run.write_text(
        json.dumps(
            {
                "adapter_sha256": "sha256:" + adapter,
                "prediction_artifact_sha256": "sha256:" + prediction,
            }
        )
    )
    score.write_text(
        json.dumps(
            {
                "adapter_sha256": "sha256:" + adapter,
                "prediction_artifact_sha256": "sha256:" + prediction,
                "execution_artifact_sha256": "sha256:" + execution,
            }
        )
    )
    spec = {
        "expected_adapter_sha256": adapter,
        "r2_predictions_sha256": prediction,
        "r2_scores_sha256": execution,
    }
    verify_model_identity(spec, {"run_manifest": run, "score_manifest": score})
    spec["expected_adapter_sha256"] = "d" * 64
    with pytest.raises(RuntimeError, match="adapter identity"):
        verify_model_identity(spec, {"run_manifest": run, "score_manifest": score})



def test_unknown_terminal_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="unknown terminal"):
        terminal_summary([{"terminal_classification": "new_unreviewed_state"}])
