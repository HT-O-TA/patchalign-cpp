from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.audit_data_v2_supply import (
    assign_split,
    feature_flags,
    matches_external_alias,
    normalized_family,
    select_proposal,
    target_report,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads(
        (ROOT / "configs/data/data_v2_supply_audit_v1.json").read_text(
            encoding="utf-8"
        )
    )


def row(index: int, **updates: object) -> dict:
    value = {
        "candidate_id": f"dv2-{index}",
        "stable_id": f"{index:064x}",
        "source_dataset": "RunBugRun",
        "source_shard": "cpp_train0.jsonl.gz",
        "split": "train",
        "family_hash": f"sha256:{index:064x}",
        "source_id_hash": f"sha256:{index + 1:064x}",
        "payload_hash": f"{index + 2:064x}",
        "new_family": True,
        "task_level": "function",
        "edit_type": "multi_line_local",
        "changed_lines": 3,
        "code_lines": 120,
        "prompt_tokens": 1100,
        "target_tokens": 50,
        "sequence_tokens": 1150,
    }
    value.update(updates)
    return value


def test_frozen_config_and_leakage_boundary() -> None:
    config = load_config()
    validate_config(config)
    assert config["isolation"][
        "confirmation_or_external_gold_consumed"
    ] is False
    assert config["isolation"]["evaluation_fields_consumed"][
        "confirmation"
    ] == ["problem_id"]
    changed = copy.deepcopy(config)
    changed["isolation"]["confirmation_or_external_gold_consumed"] = True
    with pytest.raises(RuntimeError, match="gold"):
        validate_config(changed)


def test_external_alias_normalization_is_conservative() -> None:
    assert normalized_family("LLVM-Mirror/Clang") == "llvmmirrorclang"
    assert matches_external_alias("llvm-mirror/clang", ["llvm"])
    assert matches_external_alias("ZeroMQ/libzmq", ["libzmq"])
    assert not matches_external_alias("owner/unrelated", ["llvm", "libzmq"])


def test_split_assignment_preserves_existing_and_runbugrun() -> None:
    existing = {"repo/family": "validation"}
    assert (
        assign_split(
            "commitpackft", "repo/family", "unassigned", existing, 10, 7
        )
        == "validation"
    )
    assert (
        assign_split(
            "runbugrun", "new-problem", "train", existing, 10, 7
        )
        == "train"
    )
    assert (
        assign_split(
            "runbugrun", "valid-problem", "validation", existing, 10, 7
        )
        == "validation"
    )
    assert assign_split(
        "commitpackft", "new/repo", "unassigned", {}, 10, 7
    ) in {"train", "validation"}


def test_features_and_proposal_are_deterministic() -> None:
    config = load_config()
    rows = [
        row(
            3,
            edit_type="single_line",
            code_lines=30,
            prompt_tokens=400,
            new_family=False,
        ),
        row(
            2,
            edit_type="localized_refactor",
            task_level="file_window",
            source_dataset="CommitPackFT",
        ),
        row(1, edit_type="add_helper", source_dataset="CommitPackFT"),
    ]
    assert feature_flags(rows[1], config) == {
        "new_family": True,
        "code_lines_ge_100": True,
        "prompt_tokens_ge_1024": True,
        "complex_edit": True,
        "structural_edit": True,
        "file_window": True,
        "commitpackft": True,
    }
    first = select_proposal(rows, "train", config)
    second = select_proposal(list(reversed(rows)), "train", config)
    assert [item["candidate_id"] for item in first] == [
        item["candidate_id"] for item in second
    ]
    assert first[0]["edit_type"] in {
        "localized_refactor",
        "add_helper",
    }


def test_target_report_is_simultaneous_not_marginal() -> None:
    config = load_config()
    config["provisional_increment"]["train"] = {
        "total": 2,
        "minimum_new_family": 2,
        "minimum_code_lines_ge_100": 2,
        "minimum_prompt_tokens_ge_1024": 2,
        "minimum_complex_edit": 2,
        "minimum_structural_edit": 1,
        "minimum_file_window": 1,
        "minimum_commitpackft": 1,
    }
    rows = [
        row(
            1,
            edit_type="localized_refactor",
            task_level="file_window",
            source_dataset="CommitPackFT",
        ),
        row(2),
    ]
    report = target_report(rows, "train", config)
    assert report["all_passed"] is True
    assert all(report["checks"].values())
