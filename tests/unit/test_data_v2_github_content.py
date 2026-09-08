from __future__ import annotations

import base64
import json
from pathlib import Path

from scripts.data.data_v2_github_content import (
    analyze_diff,
    parse_name_status_z,
    parse_numstat_z,
    project_commit,
    project_license,
    project_pr_commits,
    project_pr_files,
)
from scripts.data.prepare_data_v2_github_execution_feasibility_content import (
    git_environment,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


def rules() -> dict:
    return {
        "commit_and_diff": {
            "production_extensions": [".cc", ".cpp", ".h"],
            "test_path_components": ["test", "tests"],
            "required_production_targets": 1,
            "minimum_test_files": 1,
            "build_manifest_names": ["CMakeLists.txt"],
            "build_manifest_suffixes": [".cmake"],
        }
    }


def test_static_content_config_binds_fixed_selection() -> None:
    config = json.loads(
        (ROOT / "configs/data/data_v2_github_execution_feasibility_content_v1.json").read_text()
    )
    validate_config(config)
    assert config["selection"]["slurm_job_id"] == 97278
    assert config["selection"]["candidates"]["count"] == 20
    assert config["scope"]["untrusted_build_executed"] is False


def test_commit_and_pr_commit_projection_enforce_graph_identity() -> None:
    fixed = "a" * 40
    parent = "b" * 40
    head = "c" * 40
    projection, reason = project_commit(
        {"sha": fixed, "parents": [{"sha": parent}, {"sha": head}]},
        fixed,
        head,
    )
    assert reason == "selected"
    assert projection == {
        "fixed_commit_sha": fixed,
        "parent_commit_sha": parent,
        "parent_count": 2,
        "second_parent_sha": head,
    }
    assert project_commit(
        {"sha": fixed, "parents": [{"sha": parent}, {"sha": "d" * 40}]},
        fixed,
        head,
    )[1] == "merge_second_parent_not_head"
    commits, reason = project_pr_commits(
        [{"sha": parent}, {"sha": head}], head, 100
    )
    assert reason == "selected"
    assert commits["last_sha"] == head


def test_pr_file_projection_drops_patch_and_rejects_rename() -> None:
    document = [
        {
            "filename": "src/fix.cpp",
            "status": "modified",
            "additions": 1,
            "deletions": 1,
            "patch": "must not be projected",
            "sha": "must not be projected",
        }
    ]
    projection, reason = project_pr_files(document, 1, 100)
    assert reason == "selected"
    assert projection["files"] == [
        {
            "path": "src/fix.cpp",
            "status": "modified",
            "additions": 1,
            "deletions": 1,
        }
    ]
    assert "must not be projected" not in json.dumps(projection)
    document[0]["status"] = "renamed"
    assert project_pr_files(document, 1, 100)[1] == "pr_file_status_unsupported"


def test_historical_license_projection_keeps_hash_not_content() -> None:
    document = {
        "path": "LICENSE",
        "license": {"spdx_id": "MIT", "key": "mit"},
        "content": base64.b64encode(b"license text").decode("ascii"),
    }
    projection, reason = project_license(document, {"MIT"})
    assert reason == "selected"
    assert projection["spdx_id"] == "MIT"
    assert projection["content_sha256"].startswith("sha256:")
    assert "content" not in projection


def test_nul_git_parsers_and_static_diff_happy_path() -> None:
    name_status = parse_name_status_z(
        b"M\0src/fix.cpp\0A\0tests/fix_test.cpp\0"
    )
    numstat = parse_numstat_z(b"1\t1\tsrc/fix.cpp\0\t5\t0\ttests/fix_test.cpp\0".replace(b"\0\t", b"\0"))
    pr_files = [
        {"path": "src/fix.cpp", "status": "modified", "additions": 1, "deletions": 1},
        {"path": "tests/fix_test.cpp", "status": "added", "additions": 5, "deletions": 0},
    ]
    diff = (
        b"diff --git a/src/fix.cpp b/src/fix.cpp\n"
        b"index 1111111..2222222 100644\n"
        b"--- a/src/fix.cpp\n"
        b"+++ b/src/fix.cpp\n"
        b"@@ -1 +1 @@\n"
        b"-old\n"
        b"+new\n"
    )
    projection, reason = analyze_diff(
        name_status=name_status,
        numstat=numstat,
        pr_files=pr_files,
        target_diff=diff,
        target_parent_content=b"old\n",
        target_fixed_content=b"new\n",
        config=rules(),
    )
    assert reason == "selected"
    assert projection["target_path"] == "src/fix.cpp"
    assert projection["target_old_ranges"] == [[1, 1]]


def test_static_diff_rejects_missing_test_and_api_mismatch() -> None:
    name_status = [{"status": "M", "path": "src/fix.cpp"}]
    numstat = [{"path": "src/fix.cpp", "additions": 1, "deletions": 1}]
    pr_files = [
        {"path": "src/fix.cpp", "status": "modified", "additions": 1, "deletions": 1}
    ]
    diff = (
        b"diff --git a/src/fix.cpp b/src/fix.cpp\n"
        b"index 1..2 100644\n--- a/src/fix.cpp\n+++ b/src/fix.cpp\n"
        b"@@ -1 +1 @@\n-old\n+new\n"
    )
    assert analyze_diff(
        name_status=name_status,
        numstat=numstat,
        pr_files=pr_files,
        target_diff=diff,
        target_parent_content=b"old\n",
        target_fixed_content=b"new\n",
        config=rules(),
    )[1] == "test_file_missing"
    pr_files[0]["additions"] = 2
    assert analyze_diff(
        name_status=name_status,
        numstat=numstat,
        pr_files=pr_files,
        target_diff=diff,
        target_parent_content=b"old\n",
        target_fixed_content=b"new\n",
        config=rules(),
    )[1] == "local_diff_does_not_match_pr_files"


def test_git_environment_does_not_forward_home_or_tokens() -> None:
    environment = git_environment()
    assert "HOME" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"

