from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.external import a3_defects4c_external_common as external
from scripts.external.aggregate_defects4c_scores import summarize
from scripts.external.score_defects4c_case import early_result


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/external/a3_defects4c_external_v1.json"


def test_external_early_result_preserves_raw_prediction_identity() -> None:
    prediction = {"sample_id": "d4c-example", "status": "ok", "raw_text": "not a diff"}
    result = early_result("m0", prediction, "parse_failed", "invalid diff")
    assert result["case_id"] == "d4c-example"
    assert result["raw_prediction_sha256"].startswith("sha256:")
    assert result["evaluated_patch_sha256"] is None
    assert result["terminal_classification"] == "parse_failed"
    assert result["success"] is False


def test_external_summary_counts_only_executed_apply_stage() -> None:
    parse_failed = early_result(
        "m0",
        {"sample_id": "parse", "status": "ok", "raw_text": "bad"},
        "parse_failed",
        "invalid diff",
    )
    prepare_failed = {
        **early_result(
            "m0",
            {"sample_id": "prepare", "status": "ok", "raw_text": "diff"},
            "prepare_failed",
            "checkout failed",
        ),
        "evaluated_patch_sha256": "sha256:" + "0" * 64,
        "rootfs_result": {"stages": {"prepare": {"returncode": 1}}},
    }
    success = {
        **early_result(
            "m0",
            {"sample_id": "success", "status": "ok", "raw_text": "diff"},
            "success",
            "",
        ),
        "success": True,
        "evaluated_patch_sha256": "sha256:" + "1" * 64,
        "rootfs_result": {
            "stages": {
                "apply": {"returncode": 0},
                "build": {"returncode": 0},
                "test": {"returncode": 0},
            }
        },
    }
    summary = summarize([parse_failed, prepare_failed, success])
    assert summary["counts"] == {
        "total": 3,
        "parse_success": 2,
        "policy_success": 2,
        "apply_success": 1,
        "build_success": 1,
        "test_pass_at_1": 1,
        "timeouts": 0,
    }


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_without_cluster_artifacts(monkeypatch: pytest.MonkeyPatch, config: dict) -> None:
    monkeypatch.setattr(external, "verify_training_artifact", lambda _: {})
    external.validate_config(config)


def test_defects4c_external_config_is_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config()
    validate_without_cluster_artifacts(monkeypatch, config)
    assert config["dataset"] == {
        "root": "/mingli01/data/patchalign-cpp/external/defects4c/qualified-v1",
        "manifest": "manifest.json",
        "prompts": "prompts.jsonl",
        "manifest_sha256": "sha256:0728c6028328adfecb968e42351c909f4ea95a24f24a0e355d2739e97b028631",
        "prompts_sha256": "sha256:b23663fcc7fc304fb8f27b4b5c7f8adfc0da01eedf429a19c707adef0f65484f",
        "case_count": 176,
    }
    assert config["scoring"]["apply_command"] == ["git", "apply", "--recount"]
    assert config["scoring"]["sanitizer"] == "only_if_official_metadata_applies"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("dataset", "case_count"), 175),
        (("dataset", "manifest_sha256"), "sha256:" + "0" * 64),
        (("generation", "do_sample"), True),
        (("scoring", "apply_command"), ["git", "apply"]),
        (("scoring", "sanitizer"), "always"),
        (("quality_gates", "external_pass_at_1_maximum_degradation"), 0.03),
    ],
)
def test_defects4c_external_config_rejects_drift(
    monkeypatch: pytest.MonkeyPatch, path: tuple[str, ...], value: object
) -> None:
    config = copy.deepcopy(load_config())
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    monkeypatch.setattr(external, "verify_training_artifact", lambda _: {})
    with pytest.raises(RuntimeError):
        external.validate_config(config)
