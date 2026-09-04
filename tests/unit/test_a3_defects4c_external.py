from scripts.external.aggregate_defects4c_scores import summarize
from scripts.external.score_defects4c_case import early_result


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
