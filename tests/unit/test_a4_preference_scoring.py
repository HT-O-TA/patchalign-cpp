from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from scripts.preference.a4_score_common import TERMINAL_ORDER, choose_pair, ranking_key, validate_config


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/evaluation/a4_preference_scoring_v1.json"


def score(index: int, terminal: str, timed_out: bool = False) -> dict:
    stages = {name: {"status": "not_run"} for name in ("parse", "policy", "apply", "build", "public", "hidden", "regression")}
    stages["build"] = {"status": "failed" if terminal == "build_failed" else "not_run", "timed_out": timed_out}
    return {"candidate_index": index, "terminal_classification": terminal, "stages": stages}


def test_frozen_a4_scoring_config_is_accepted() -> None:
    validate_config(json.loads(CONFIG.read_text(encoding="utf-8")))


def test_changed_ranking_and_a5_boundary_fail_closed() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    changed = copy.deepcopy(config)
    changed["ranking"]["uses_gold_patch_similarity"] = True
    with pytest.raises(RuntimeError, match="ranking"):
        validate_config(changed)
    changed = copy.deepcopy(config)
    changed["a5"]["automatically_authorized"] = True
    with pytest.raises(RuntimeError, match="A5"):
        validate_config(changed)


def test_terminal_stage_and_timeout_ranking() -> None:
    for low, high in zip(TERMINAL_ORDER, TERMINAL_ORDER[1:]):
        assert ranking_key(score(0, low)) < ranking_key(score(1, high))
    assert ranking_key(score(0, "build_failed", True)) < ranking_key(score(1, "build_failed", False))


def test_pair_uses_strongest_contrast_and_lowest_index_for_ties() -> None:
    scores = [score(0, "parse_failed"), score(1, "success"), score(2, "success"), score(3, "parse_failed")]
    chosen, rejected = choose_pair(scores)
    assert chosen["candidate_index"] == 1
    assert rejected["candidate_index"] == 0
    assert choose_pair([score(i, "apply_failed") for i in range(4)]) is None


def test_pair_schema_accepts_training_only_record() -> None:
    schema = json.loads((ROOT / "schemas/a4-preference-pair-v0.1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    value = {
        "schema_version": "0.1.0", "pair_id": "a4-pair-" + "0" * 20,
        "case_id": "case", "source_train_sample_id": "train", "task_level": "function",
        "prompt_version": "a4-cpp-repair-v1", "prompt_sha256": "sha256:" + "1" * 64,
        "prompt": "repair", "chosen": {"candidate_id": "c1", "candidate_index": 0, "response_sha256": "sha256:" + "2" * 64, "response": "good"},
        "rejected": {"candidate_id": "c2", "candidate_index": 1, "response_sha256": "sha256:" + "3" * 64, "response": "bad"},
    }
    validator = Draft202012Validator(schema)
    validator.validate(value)
    leaked = copy.deepcopy(value)
    leaked["terminal_classification"] = "success"
    with pytest.raises(ValidationError):
        validator.validate(leaked)


def test_submit_chain_is_cpu_only_and_dependency_ordered() -> None:
    submit = (ROOT / "scripts/preference/submit_a4_scoring.sh").read_text(encoding="utf-8")
    assert 'afterok:${PREFLIGHT_JOB}' in submit
    assert 'afterok:${SCORE_JOB}' in submit
    for name in ("a4_score_preflight.sbatch", "a4_score_array.sbatch", "a4_preference_finalize.sbatch"):
        text = (ROOT / "slurm" / name).read_text(encoding="utf-8")
        assert "--gres=gpu" not in text
