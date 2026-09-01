from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from patchalign.evaluation import score_prediction, summarize_scores


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "scoring"
REPO_SOURCE = FIXTURE_DIR / "tiny_cpp_repo"
EXPECTED_BASE_COMMIT = "d68a0718b4a066cb319e89efc21e5c2af9d1d093"
EXPECTED_SUCCESS_SCORE_SHA256 = (
    "sha256:199e2f57b505a9dd148bf9c57c219c8bd952ee90a2c7a74d44ed96b3a6a98dc0"
)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str], cwd: Path, *, environment: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=environment, check=True, capture_output=True, text=True)


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fixture-repo"
    shutil.copytree(REPO_SOURCE, repo)
    run(["git", "init", "--quiet"], repo)
    run(["git", "config", "user.name", "PatchAlign Fixture"], repo)
    run(["git", "config", "user.email", "fixture@patchalign.invalid"], repo)
    run(["git", "config", "commit.gpgsign", "false"], repo)
    run(["git", "config", "core.autocrlf", "false"], repo)
    run(["git", "add", "."], repo)
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        }
    )
    run(["git", "commit", "--quiet", "-m", "fixture: buggy add implementation"], repo, environment=environment)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert commit == EXPECTED_BASE_COMMIT
    return repo


def prediction_with_patch(patch_name: str) -> dict[str, object]:
    prediction = copy.deepcopy(load_json(FIXTURE_DIR / "prediction.success.json"))
    patch = (FIXTURE_DIR / "patches" / patch_name).read_text(encoding="utf-8")
    prediction["raw_text"] = patch
    prediction["extracted_patch"] = patch
    return prediction


def test_buggy_fixture_has_expected_before_fail_and_regression_pass(fixture_repo: Path) -> None:
    sample = load_json(FIXTURE_DIR / "sample.json")
    run(sample["build_command"], fixture_repo)  # type: ignore[arg-type]
    public = subprocess.run(sample["public_test_command"], cwd=fixture_repo, check=False)  # type: ignore[arg-type]
    hidden = subprocess.run(sample["hidden_test_command"], cwd=fixture_repo, check=False)  # type: ignore[arg-type]
    regression = subprocess.run(sample["regression_test_command"], cwd=fixture_repo, check=False)  # type: ignore[arg-type]
    assert public.returncode != 0
    assert hidden.returncode != 0
    assert regression.returncode == 0


def test_recount_accepts_wrong_hunk_counts_but_plain_apply_rejects(fixture_repo: Path) -> None:
    prediction = load_json(FIXTURE_DIR / "prediction.success.json")
    patch = str(prediction["raw_text"])
    plain = subprocess.run(
        ["git", "apply", "--check", "-"], cwd=fixture_repo, input=patch, text=True, check=False
    )
    recounted = subprocess.run(
        ["git", "apply", "--recount", "--check", "-"],
        cwd=fixture_repo,
        input=patch,
        text=True,
        check=False,
    )
    assert plain.returncode != 0
    assert recounted.returncode == 0


@pytest.mark.parametrize(
    ("patch_name", "classification"),
    (
        ("parse-failed.diff", "parse_failed"),
        ("policy-violation.diff", "policy_violation"),
        ("apply-failed.diff", "apply_failed"),
        ("build-failed.diff", "build_failed"),
        ("public-failed.diff", "public_test_failed"),
        ("hidden-failed.diff", "hidden_test_failed"),
        ("regression-failed.diff", "regression_failed"),
    ),
)
def test_terminal_classification(
    fixture_repo: Path, patch_name: str, classification: str
) -> None:
    score = score_prediction(
        load_json(FIXTURE_DIR / "sample.json"), prediction_with_patch(patch_name), fixture_repo
    )
    assert score["terminal_classification"] == classification
    assert score["success"] is False
    failure_stage = {
        "parse_failed": "parse",
        "policy_violation": "policy",
        "apply_failed": "apply",
        "build_failed": "build",
        "public_test_failed": "public",
        "hidden_test_failed": "hidden",
        "regression_failed": "regression",
    }[classification]
    stage_names = list(score["stages"])
    failure_index = stage_names.index(failure_stage)
    assert all(score["stages"][name]["status"] == "passed" for name in stage_names[:failure_index])
    assert score["stages"][failure_stage]["status"] == "failed"
    assert all(score["stages"][name]["status"] == "not_run" for name in stage_names[failure_index + 1 :])


def test_generation_failure_precedes_patch_parsing(fixture_repo: Path) -> None:
    prediction = load_json(FIXTURE_DIR / "prediction.success.json")
    prediction["status"] = "oom"
    prediction["raw_text"] = "not a patch"
    score = score_prediction(load_json(FIXTURE_DIR / "sample.json"), prediction, fixture_repo)
    assert score["terminal_classification"] == "generation_failed"
    assert all(stage["status"] == "not_run" for stage in score["stages"].values())


def test_build_timeout_is_recorded_and_stops_later_stages(fixture_repo: Path) -> None:
    sample = load_json(FIXTURE_DIR / "sample.json")
    sample["timeout_seconds"] = 2
    sample["build_command"] = [sys.executable, "-c", "import time; time.sleep(10)"]
    score = score_prediction(
        sample, load_json(FIXTURE_DIR / "prediction.success.json"), fixture_repo
    )
    assert score["terminal_classification"] == "build_failed"
    assert score["stages"]["build"]["timed_out"] is True
    assert score["stages"]["public"]["status"] == "not_run"
    assert summarize_scores([score])["counts"]["timeouts"] == 1


def test_prediction_file_scores_successfully_and_deterministically(fixture_repo: Path) -> None:
    sample = load_json(FIXTURE_DIR / "sample.json")
    prediction = load_json(FIXTURE_DIR / "prediction.success.json")
    first = score_prediction(sample, prediction, fixture_repo)
    second = score_prediction(sample, prediction, fixture_repo)
    assert first == second
    assert first["terminal_classification"] == "success"
    assert first["success"] is True
    assert first["score_sha256"] == EXPECTED_SUCCESS_SCORE_SHA256
    assert all(stage["status"] == "passed" for stage in first["stages"].values())

    first_summary = summarize_scores([first])
    second_summary = summarize_scores([second])
    assert first_summary == second_summary
    assert first_summary["counts"]["total"] == 1
    assert first_summary["counts"]["success"] == 1
    assert first_summary["counts"]["hidden_test_pass_at_1"] == 1
    assert first_summary["rates"]["success"] == 1.0
