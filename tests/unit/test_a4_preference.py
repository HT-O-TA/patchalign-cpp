from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.preference.build_a4_executable_candidates import (
    MODE,
    select_train_rows,
    validate_config as validate_data_config,
)
from scripts.preference.run_a4_candidate_generation import candidate_seed
from scripts.external import bind_pre_a4_readiness


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/data/a4_executable_preference_v1.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_frozen_a4_data_config_is_accepted() -> None:
    validate_data_config(load_config())


def test_a4_mode_and_leakage_boundaries_fail_closed() -> None:
    config = load_config()
    changed = copy.deepcopy(config)
    changed["mode"] = "promoted"
    with pytest.raises(RuntimeError, match="exploratory"):
        validate_data_config(changed)
    changed = copy.deepcopy(config)
    changed["leakage_policy"]["forbidden"] = ["A3.3 validation"]
    with pytest.raises(RuntimeError, match="forbidden A4 source"):
        validate_data_config(changed)


def test_train_only_selection_is_deterministic_and_family_unique(tmp_path: Path) -> None:
    rows = []
    for index in range(27):
        rows.append({
            "sample_id": f"run:formal-train:{index}:x", "source_dataset": "RunBugRun",
            "split": "train", "language": "cpp", "task_level": "file_window",
            "repo_family": f"RunBugRun:problem:file-{index}",
        })
    for index in range(2929):
        rows.append({
            "sample_id": f"run:formal-train:{index + 1000}:x", "source_dataset": "RunBugRun",
            "split": "train", "language": "cpp", "task_level": "function",
            "repo_family": f"RunBugRun:problem:function-{index}",
        })
    train = tmp_path / "train.jsonl"
    train.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    config = load_config()
    config["source"]["formal_train"] = str(train)
    first = select_train_rows(config)
    second = select_train_rows(config)
    assert [row["sample_id"] for row in first] == [row["sample_id"] for row in second]
    assert len(first) == 626
    assert sum(row["task_level"] == "function" for row in first) == 600
    assert sum(row["task_level"] == "file_window" for row in first) == 26
    assert len({row["repo_family"] for row in first}) == 626

    testable = {row["repo_family"] for row in rows}
    excluded = first[0]["repo_family"]
    filtered = select_train_rows(config, testable - {excluded})
    assert excluded not in {row["repo_family"] for row in filtered}
    assert len(filtered) == 626


def test_candidate_seed_is_stable_and_candidate_specific() -> None:
    seeds = [candidate_seed(20260830, "case-a", index) for index in range(4)]
    assert seeds == [candidate_seed(20260830, "case-a", index) for index in range(4)]
    assert len(set(seeds)) == 4
    assert seeds != [candidate_seed(20260830, "case-b", index) for index in range(4)]


def test_a4_candidate_schema_accepts_minimal_record() -> None:
    schema = json.loads((ROOT / "schemas/a4-preference-candidate-v0.1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    record = {
        "schema_version": "0.1.0", "run_id": "run", "candidate_id": "case:candidate:0",
        "case_id": "case", "source_train_sample_id": "train", "task_level": "function",
        "model": {"model_id": "model", "revision": "rev", "config_sha256": "sha256:" + "0" * 64, "adapter_sha256": "sha256:" + "1" * 64},
        "prompt_version": "a4-cpp-repair-v1", "prompt_sha256": "sha256:" + "2" * 64,
        "seed": 1, "candidate_index": 0, "generation": {}, "raw_text": "", "extracted_patch": None,
        "status": "ok", "error": None, "input_tokens": 1, "output_tokens": 0,
        "latency_seconds": 0.0, "max_gpu_memory_bytes": 0,
    }
    Draft202012Validator(schema).validate(record)


def test_submit_script_queues_gpu_after_data() -> None:
    text = (ROOT / "scripts/preference/submit_a4_exploratory.sh").read_text(encoding="utf-8")
    assert "a4_ready'] is False" in text
    assert "supplementary_confirmation_passed" in text
    assert 'dependency="afterok:${DATA_JOB}"' in text
    assert "slurm/a4_generate.sbatch" in text
    assert MODE == "owner_authorized_exploratory"


def test_readiness_binding_preserves_confirmation_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "comparison.json"
    external.write_text(json.dumps({
        "version": "a3-defects4c-external-comparison-v1",
        "denominator": 150,
        "external_gate_passed": True,
    }), encoding="utf-8")
    output = tmp_path / "binding.json"
    monkeypatch.setattr(bind_pre_a4_readiness, "EXTERNAL_PATH", str(external))
    monkeypatch.setattr(bind_pre_a4_readiness, "OUTPUT_LEDGER", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(bind_pre_a4_readiness.subprocess, "check_output", lambda *args, **kwargs: "")
    monkeypatch.setattr("sys.argv", ["bind", "--output-config", str(output)])
    bind_pre_a4_readiness.main()
    binding = json.loads(output.read_text(encoding="utf-8"))
    assert binding["required_gates"]["supplementary_confirmation_passed"] is True
    assert binding["inputs"]["confirmation"]["sha256"] == bind_pre_a4_readiness.CONFIRMATION_SHA
    assert binding["inputs"]["external"]["sha256"].startswith("sha256:")


def test_external_pipeline_queues_readiness_after_scoring() -> None:
    text = (ROOT / "scripts/external/submit_defects4c_external_pipeline.sh").read_text(encoding="utf-8")
    assert 'dependency="afterok:${M0_JOB}:${M1_JOB}"' in text
    assert 'dependency="afterok:${SCORE_JOB}"' in text
    assert 'dependency="afterok:${AGGREGATE_JOB}"' in text
    assert "a3_4_finalize_pre_a4.sbatch" in text
