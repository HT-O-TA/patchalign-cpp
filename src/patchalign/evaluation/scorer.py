"""Deterministic stage-ordered scoring for one patch prediction."""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
from typing import Any

from .patches import PatchParseError, PatchPolicyError, enforce_patch_policy, parse_unified_diff


STAGE_NAMES = ("parse", "policy", "apply", "build", "public", "hidden", "regression")


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(payload)


def _stage(status: str, **details: Any) -> dict[str, Any]:
    return {"status": status, **details}


def _not_run_stages() -> dict[str, dict[str, Any]]:
    return {name: _stage("not_run") for name in STAGE_NAMES}


def _command_result(
    command: Sequence[str], cwd: Path, timeout_seconds: int, *, stdin: str | None = None
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC", "PYTHONNOUSERSITE": "1"})
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=environment,
        text=True,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout_seconds)
        return {
            "status": "passed" if process.returncode == 0 else "failed",
            "exit_code": process.returncode,
            "timed_out": False,
            "stdout_sha256": _sha256_text(stdout),
            "stderr_sha256": _sha256_text(stderr),
        }
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        return {
            "status": "failed",
            "exit_code": None,
            "timed_out": True,
            "stdout_sha256": _sha256_text(stdout),
            "stderr_sha256": _sha256_text(stderr),
        }


def _finish(record: dict[str, Any], classification: str) -> dict[str, Any]:
    record["terminal_classification"] = classification
    record["success"] = classification == "success"
    record["score_sha256"] = _canonical_sha256(record)
    return record


def score_prediction(
    sample: dict[str, Any], prediction: dict[str, Any], base_repo: str | Path
) -> dict[str, Any]:
    """Score a prediction in an isolated clone using the frozen stage order."""

    stages = _not_run_stages()
    record: dict[str, Any] = {
        "scorer_version": "0.1.0",
        "sample_id": sample["sample_id"],
        "run_id": prediction["run_id"],
        "base_commit": sample["base_commit"],
        "prediction_sha256": _sha256_text(prediction.get("raw_text", "")),
        "stages": stages,
    }

    if prediction.get("sample_id") != sample.get("sample_id"):
        stages["parse"] = _stage("failed", reason="sample_id_mismatch")
        return _finish(record, "parse_failed")
    if prediction.get("status") != "ok":
        return _finish(record, "generation_failed")

    raw_text = prediction.get("raw_text", "")
    try:
        parsed = parse_unified_diff(raw_text)
    except PatchParseError as error:
        stages["parse"] = _stage("failed", reason=str(error))
        return _finish(record, "parse_failed")
    stages["parse"] = _stage("passed", file_count=len(parsed.files))

    try:
        changed_paths = enforce_patch_policy(parsed, list(sample["allowed_paths"]))
    except PatchPolicyError as error:
        stages["policy"] = _stage("failed", reason=str(error))
        return _finish(record, "policy_violation")
    stages["policy"] = _stage("passed", changed_paths=list(changed_paths))

    base_repo_path = Path(base_repo).resolve()
    timeout_seconds = int(sample["timeout_seconds"])
    with tempfile.TemporaryDirectory(prefix="patchalign-score-") as temporary_directory:
        worktree = Path(temporary_directory) / "repo"
        clone = _command_result(
            ["git", "clone", "--quiet", "--no-hardlinks", str(base_repo_path), str(worktree)],
            base_repo_path.parent,
            timeout_seconds,
        )
        if clone["status"] != "passed":
            stages["apply"] = {**clone, "reason": "fixture_clone_failed"}
            return _finish(record, "apply_failed")
        checkout = _command_result(
            ["git", "checkout", "--quiet", "--detach", sample["base_commit"]],
            worktree,
            timeout_seconds,
        )
        if checkout["status"] != "passed":
            stages["apply"] = {**checkout, "reason": "base_commit_checkout_failed"}
            return _finish(record, "apply_failed")

        apply_check = _command_result(
            ["git", "apply", "--recount", "--check", "-"],
            worktree,
            timeout_seconds,
            stdin=raw_text,
        )
        if apply_check["status"] != "passed":
            stages["apply"] = {**apply_check, "reason": "git_apply_check_failed"}
            return _finish(record, "apply_failed")
        apply_result = _command_result(
            ["git", "apply", "--recount", "-"], worktree, timeout_seconds, stdin=raw_text
        )
        stages["apply"] = apply_result
        if apply_result["status"] != "passed":
            return _finish(record, "apply_failed")

        commands = (
            ("build", sample["build_command"], "build_failed"),
            ("public", sample["public_test_command"], "public_test_failed"),
            ("hidden", sample["hidden_test_command"], "hidden_test_failed"),
            ("regression", sample["regression_test_command"], "regression_failed"),
        )
        for stage_name, command, failure_classification in commands:
            if command is None:
                stages[stage_name] = _stage("failed", reason="required_command_missing")
                return _finish(record, failure_classification)
            result = _command_result(command, worktree, timeout_seconds)
            stages[stage_name] = result
            if result["status"] != "passed":
                return _finish(record, failure_classification)

    return _finish(record, "success")


def summarize_scores(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Create a deterministic, fixed-denominator summary."""

    denominator = len(records)

    def passed(stage_name: str) -> int:
        return sum(record["stages"][stage_name]["status"] == "passed" for record in records)

    successes = sum(record["terminal_classification"] == "success" for record in records)
    regression_failures = sum(
        record["terminal_classification"] == "regression_failed" for record in records
    )
    format_violations = sum(
        record["terminal_classification"] in {"parse_failed", "policy_violation"}
        for record in records
    )
    timeouts = sum(
        any(stage.get("timed_out", False) for stage in record["stages"].values())
        for record in records
    )
    counts = {
        "total": denominator,
        "parse_success": passed("parse"),
        "apply_success": passed("apply"),
        "compile_success": passed("build"),
        "public_test_success": passed("public"),
        "hidden_stage_success": passed("hidden"),
        "hidden_test_pass_at_1": successes,
        "regression_failures": regression_failures,
        "format_violations": format_violations,
        "timeouts": timeouts,
        "success": successes,
    }
    rates = {
        key: (value / denominator if denominator else 0.0)
        for key, value in counts.items()
        if key != "total"
    }
    summary: dict[str, Any] = {"scorer_version": "0.1.0", "counts": counts, "rates": rates}
    summary["summary_sha256"] = _canonical_sha256(summary)
    return summary
