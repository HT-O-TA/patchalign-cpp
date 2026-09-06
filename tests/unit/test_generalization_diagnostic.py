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


def test_unknown_terminal_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="unknown terminal"):
        terminal_summary([{"terminal_classification": "new_unreviewed_state"}])
