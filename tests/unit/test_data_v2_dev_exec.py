from __future__ import annotations

from scripts.data.qualify_data_v2_dev_exec import a4_selected_orders, eligible_orders


def test_eligible_orders_excludes_a4_and_non_function_cases() -> None:
    items = [
        {"candidate_order": 4, "case_id": "a", "source_dataset": "RunBugRun", "upstream_split": "train", "task_level": "function"},
        {"candidate_order": 1, "case_id": "b", "source_dataset": "RunBugRun", "upstream_split": "train", "task_level": "function"},
        {"candidate_order": 2, "case_id": "c", "source_dataset": "RunBugRun", "upstream_split": "train", "task_level": "file_window"},
        {"candidate_order": 3, "case_id": "d", "source_dataset": "RunBugRun", "upstream_split": "validation", "task_level": "function"},
    ]
    assert eligible_orders(items, {4}) == [1]


def test_a4_selected_order_uses_frozen_source_field() -> None:
    cases = [{"source_candidate_order": 7}, {"source_candidate_order": 3}]
    assert a4_selected_orders(cases) == {3, 7}
