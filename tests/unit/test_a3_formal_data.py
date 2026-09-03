from __future__ import annotations

import json
from pathlib import Path

from scripts.data.build_a3_formal_holdout import formal_level as holdout_level
from scripts.data.build_a3_formal_sft_data import (
    EDIT_TARGETS,
    TARGETS,
    classify_edit,
    formal_level,
)


ROOT = Path(__file__).resolve().parents[2]


def test_nested_change_is_function_level() -> None:
    old = """int main() {
    if (true) {
        return 1;
    }
}
"""
    new = old.replace("return 1;", "return 0;")
    assert formal_level(old, "main.cpp", new) == "function"
    assert holdout_level(old, [3]) == "function"


def test_top_level_change_is_file_window() -> None:
    old = "int value = 1;\nint main() { return value; }\n"
    new = "int value = 2;\nint main() { return value; }\n"
    assert formal_level(old, "main.cpp", new) == "file_window"


def test_add_helper_requires_definition_and_call() -> None:
    old = "int main() { return 1; }\n"
    new = (
        "int answer() { return 2; }\n"
        "int main() { return answer(); }\n"
    )
    assert classify_edit(old, new, 2) == "add_helper"
    assert classify_edit(old, old.replace("1", "2"), 1) == "single_line"


def test_frozen_formal_data_config_matches_builder_targets() -> None:
    config = json.loads((ROOT / "configs/data/a3_formal_v1.json").read_text())
    source_names = {"commitpackft": "CommitPackFT", "runbugrun": "RunBugRun"}
    for split in ("train", "validation"):
        cells = config["formal_sft"]["source_task_cells"][split]
        expected = {
            (source, level): cells[source_names[source]][level]
            for source in source_names
            for level in ("function", "file_window")
        }
        assert TARGETS[split] == expected
        assert sum(expected.values()) == config["formal_sft"]["counts"][split]
        assert {
            source_names[source]: sum(
                expected[(source, level)]
                for level in ("function", "file_window")
            )
            for source in source_names
        } == config["formal_sft"]["source_counts"][split]
        assert {
            level: sum(
                expected[(source, level)]
                for source in source_names
            )
            for level in ("function", "file_window")
        } == config["formal_sft"]["task_level_counts"][split]
        assert EDIT_TARGETS[split] == config["formal_sft"]["edit_type_targets"][split]
        assert sum(EDIT_TARGETS[split].values()) == config["formal_sft"]["counts"][split]
