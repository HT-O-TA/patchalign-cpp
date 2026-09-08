#!/usr/bin/env python3
"""Acquire and statically qualify the fixed 20-case GitHub content denominator."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Mapping
from urllib.parse import quote

from scripts.data.collect_data_v2_github_detail_pilot import (
    GitHubClient,
    checkpointed_request,
)
from scripts.data.data_v2_github_content import (
    analyze_diff,
    is_test_path,
    parse_name_status_z,
    parse_numstat_z,
    project_commit,
    project_license,
    project_pr_commits,
    project_pr_files,
)


VERSION = "data-v2-github-execution-feasibility-content-v1"
DEFAULT_CONFIG = Path(
    "configs/data/data_v2_github_execution_feasibility_content_v1.json"
)
SHA_RE = re.compile(r"[0-9a-f]{40}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    require(all(isinstance(row, dict) for row in rows), f"invalid JSONL: {path}")
    return rows


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for row in rows
    )


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_file(spec: Mapping[str, Any], label: str) -> Path:
    path = Path(str(spec["path"]))
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return path


def current_commit() -> str:
    value = os.environ.get("PATCHALIGN_GIT_COMMIT", "").strip()
    if not value:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    require(SHA_RE.fullmatch(value) is not None, "invalid Git commit")
    return value


def validate_config(config: Mapping[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected content version")
    verify_file(config["decision"], "ADR-0021")
    selection = config["selection"]
    require(
        selection["version"]
        == "data-v2-github-execution-feasibility-selection-v1",
        "selection version changed",
    )
    require(
        selection["git_commit"] == "b4383db87048a88d504a31109e291dbf2a0516d9",
        "selection commit changed",
    )
    require(selection["slurm_job_id"] == 97278, "selection Job changed")
    require(selection["candidates"]["count"] == 20, "fixed denominator changed")
    for key in ("candidates", "summary", "run_manifest"):
        verify_file(selection[key], f"selection {key}")
    summary = load_json(Path(selection["summary"]["path"]))
    require(summary["fixed_denominator"] == 20, "selection denominator changed")
    require(summary["unique_repositories"] == 20, "selection repositories changed")
    require(summary["replacement_allowed"] is False, "selection replacement changed")
    manifest = load_json(Path(selection["run_manifest"]["path"]))
    require(manifest["git_commit"] == selection["git_commit"], "selection manifest commit changed")
    require(str(manifest["slurm_job_id"]) == str(selection["slurm_job_id"]), "selection manifest Job changed")
    require(manifest["config_sha256"] == selection["config_sha256"], "selection config changed")
    require(manifest["script_sha256"] == selection["script_sha256"], "selection script changed")
    require(
        manifest["outputs"]["selected-candidates.jsonl"]["sha256"]
        == selection["candidates"]["sha256"],
        "selection reverse binding changed",
    )
    require(
        manifest["outputs"]["summary.json"]["sha256"]
        == selection["summary"]["sha256"],
        "selection summary reverse binding changed",
    )
    require(
        config["scope"]
        == {
            "fixed_candidate_content_acquisition_authorized": True,
            "github_api_metadata_and_license_only": True,
            "git_fetch_fixed_objects_only": True,
            "raw_api_response_stored": False,
            "repository_content_cluster_local": True,
            "untrusted_build_executed": False,
            "training_admitted": False,
            "gpu_authorized": False,
            "dpo_authorized": False,
        },
        "scope changed",
    )
    api = config["api"]
    require(api["base_url"] == "https://api.github.com", "API base changed")
    require(api["maximum_attempts"] == 3, "API retry policy changed")
    require(api["maximum_logical_requests"] == 100, "API logical budget changed")
    require(api["maximum_network_attempts_per_run"] == 106, "API attempt budget changed")
    require(api["unauthenticated_minimum_interval_seconds"] >= 61.0, "anonymous throttle weakened")
    require(api["authenticated_minimum_interval_seconds"] >= 0.5, "authenticated throttle weakened")
    require(api["pr_commits_per_page"] == 100, "commit page size changed")
    require(api["pr_files_per_page"] == 100, "file page size changed")
    git = config["git"]
    require(git["binary"] == "/usr/bin/git", "Git path changed")
    require(git["version"] == "git version 2.34.1", "Git version changed")
    require(
        git["sha256"]
        == "sha256:587ef21868c948b883993e23209b86a72a6ddc06aab1545c697ffc31075acd4a",
        "Git hash changed",
    )
    require(git["remote_template"] == "https://github.com/{repository_full_name}.git", "remote template changed")
    require(git["fetch_depth"] == 2, "fetch depth changed")
    require(git["fetch_timeout_seconds"] == 1200, "fetch timeout changed")
    require(git["maximum_fetches"] == 20, "fetch budget changed")
    require(git["maximum_repository_bytes"] == 1610612736, "repository byte cap changed")
    require(git["maximum_total_repository_bytes"] == 21474836480, "total byte cap changed")
    require(git["submodules_allowed"] is False, "submodules enabled")
    rules = config["commit_and_diff"]
    require(rules["merge_commit_parent_counts"] == [1, 2], "parent counts changed")
    require(rules["require_last_pr_commit_equals_head_sha"] is True, "PR commit gate changed")
    require(rules["require_local_parent_to_fixed_diff_matches_pr_files"] is True, "diff gate changed")
    require(rules["renames_copies_binary_mode_changes_allowed"] is False, "diff types changed")
    require(rules["required_production_targets"] == 1, "production target count changed")
    require(rules["minimum_test_files"] == 1, "test file minimum changed")
    require(rules["production_target_must_be_modified_existing_utf8_text"] is True, "target gate changed")
    require(rules["outside_test_build_manifest_delta_allowed"] is False, "build delta gate changed")
    require(rules["required_root_build_manifest"] == "CMakeLists.txt", "build profile changed")
    require(config["license"]["check_at_parent_and_fixed"] is True, "historical license gate changed")
    require(config["license"]["require_nonempty_content_sha256"] is True, "license hash gate changed")
    require(
        config["content_root"]
        == "/mingli01/data/patchalign-cpp/data-v2/github-executable-evidence-v2/feasibility-content-v1",
        "content root changed",
    )
    require(
        config["output_directory"]
        == "artifacts/data-v2/github-executable-evidence-v2/feasibility-content-v1",
        "output path changed",
    )


def validate_selection(rows: list[dict[str, Any]]) -> None:
    require(len(rows) == 20, "fixed denominator changed")
    require([row["feasibility_order"] for row in rows] == list(range(20)), "selection order changed")
    require(len({row["candidate_id"] for row in rows}) == 20, "duplicate candidate")
    require(len({row["repository_split_group"] for row in rows}) == 20, "duplicate repository")
    counts = Counter((row["projected_split"], row["selection_stratum"]) for row in rows)
    require(
        counts
        == Counter(
            {
                ("train", "bug_label"): 8,
                ("train", "no_bug_label"): 8,
                ("validation", "bug_label"): 2,
                ("validation", "no_bug_label"): 2,
            }
        ),
        "selection strata changed",
    )
    require(all(row["replacement_allowed"] is False for row in rows), "replacement enabled")


def git_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/false",
            "GIT_LFS_SKIP_SMUDGE": "1",
        }
    )
    return environment


def git_command(config: Mapping[str, Any], git_dir: Path, *args: str) -> list[str]:
    return [
        config["git"]["binary"],
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "core.hooksPath=/dev/null",
        f"--git-dir={git_dir}",
        *args,
    ]


def run_git(
    config: Mapping[str, Any],
    git_dir: Path,
    *args: str,
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        git_command(config, git_dir, *args),
        capture_output=True,
        env=git_environment(),
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Git command failed ({result.returncode}): {args[0]}: "
            + result.stderr[-1000:].decode("utf-8", errors="replace")
        )
    return result


def tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def object_exists(
    config: Mapping[str, Any], git_dir: Path, object_name: str
) -> bool:
    return (
        run_git(config, git_dir, "cat-file", "-e", object_name, check=False).returncode
        == 0
    )


def git_show(
    config: Mapping[str, Any], git_dir: Path, commit: str, path: str
) -> bytes:
    return run_git(config, git_dir, "show", f"{commit}:{path}").stdout


def prepare_git_content(
    config: Mapping[str, Any],
    candidate: Mapping[str, Any],
    commit_projection: Mapping[str, Any],
    pr_files_projection: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    content_root = Path(config["content_root"])
    final = content_root / candidate["candidate_id"]
    temporary = content_root / (candidate["candidate_id"] + ".building")
    require(not final.exists(), f"content exists without checkpoint: {final}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    git_dir = temporary / "repository.git"
    evidence: dict[str, Any] = {}
    try:
        init = subprocess.run(
            [config["git"]["binary"], "init", "--bare", str(git_dir)],
            capture_output=True,
            env=git_environment(),
            timeout=60,
        )
        require(init.returncode == 0, "git init failed")
        remote = config["git"]["remote_template"].format(
            repository_full_name=candidate["pr"]["repository_full_name"]
        )
        require(
            remote
            == "https://github.com/"
            + candidate["pr"]["repository_full_name"]
            + ".git",
            "remote identity changed",
        )
        run_git(config, git_dir, "remote", "add", "origin", remote)
        fixed = commit_projection["fixed_commit_sha"]
        parent = commit_projection["parent_commit_sha"]
        fetch = run_git(
            config,
            git_dir,
            "fetch",
            "--no-tags",
            "--no-write-fetch-head",
            "--depth",
            str(config["git"]["fetch_depth"]),
            "origin",
            fixed,
            parent,
            timeout=config["git"]["fetch_timeout_seconds"],
            check=False,
        )
        evidence["fetch"] = {
            "returncode": fetch.returncode,
            "stdout_sha256": sha256_bytes(fetch.stdout),
            "stderr_sha256": sha256_bytes(fetch.stderr),
        }
        if fetch.returncode != 0:
            shutil.rmtree(temporary)
            return None, "git_fetch_failed", evidence
        repository_bytes = tree_size(git_dir)
        evidence["repository_bytes"] = repository_bytes
        if repository_bytes > config["git"]["maximum_repository_bytes"]:
            shutil.rmtree(temporary)
            return None, "repository_byte_limit_exceeded", evidence
        if not object_exists(config, git_dir, fixed + "^{commit}"):
            shutil.rmtree(temporary)
            return None, "fixed_commit_missing_after_fetch", evidence
        if not object_exists(config, git_dir, parent + "^{commit}"):
            shutil.rmtree(temporary)
            return None, "parent_commit_missing_after_fetch", evidence
        if object_exists(config, git_dir, fixed + ":.gitmodules") or object_exists(
            config, git_dir, parent + ":.gitmodules"
        ):
            temporary.replace(final)
            evidence["content_directory"] = str(final)
            return None, "submodules_unsupported", evidence
        root_manifest = config["commit_and_diff"]["required_root_build_manifest"]
        if not object_exists(config, git_dir, fixed + ":" + root_manifest) or not object_exists(
            config, git_dir, parent + ":" + root_manifest
        ):
            temporary.replace(final)
            evidence["content_directory"] = str(final)
            return None, "root_cmake_manifest_missing", evidence
        name_status_raw = run_git(
            config,
            git_dir,
            "diff",
            "--name-status",
            "--no-renames",
            "-z",
            parent,
            fixed,
        ).stdout
        numstat_raw = run_git(
            config,
            git_dir,
            "diff",
            "--numstat",
            "--no-renames",
            "-z",
            parent,
            fixed,
        ).stdout
        summary_raw = run_git(
            config,
            git_dir,
            "diff",
            "--summary",
            "--no-renames",
            parent,
            fixed,
        ).stdout
        evidence["local_diff"] = {
            "name_status_sha256": sha256_bytes(name_status_raw),
            "numstat_sha256": sha256_bytes(numstat_raw),
            "summary_sha256": sha256_bytes(summary_raw),
        }
        if b"mode change" in summary_raw or b"rename " in summary_raw or b"copy " in summary_raw:
            temporary.replace(final)
            evidence["content_directory"] = str(final)
            return None, "unsupported_diff_metadata", evidence
        try:
            name_status = parse_name_status_z(name_status_raw)
            numstat = parse_numstat_z(numstat_raw)
        except (UnicodeDecodeError, ValueError) as error:
            temporary.replace(final)
            evidence["content_directory"] = str(final)
            return None, "local_diff_invalid:" + str(error), evidence
        test_components = {
            value.casefold()
            for value in config["commit_and_diff"]["test_path_components"]
        }
        candidate_targets = [
            row["path"]
            for row in name_status
            if row["status"] == "M"
            and not is_test_path(row["path"], test_components)
            and Path(row["path"]).suffix.casefold()
            in {
                value.casefold()
                for value in config["commit_and_diff"]["production_extensions"]
            }
        ]
        analysis: dict[str, Any] | None = None
        reason = "production_target_count_mismatch"
        if candidate_targets:
            target = candidate_targets[0]
            target_diff = run_git(
                config,
                git_dir,
                "diff",
                "--unified=0",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                parent,
                fixed,
                "--",
                target,
            ).stdout
            analysis, reason = analyze_diff(
                name_status=name_status,
                numstat=numstat,
                pr_files=pr_files_projection["files"],
                target_diff=target_diff,
                target_parent_content=git_show(config, git_dir, parent, target),
                target_fixed_content=git_show(config, git_dir, fixed, target),
                config=config,
            )
        temporary.replace(final)
        evidence["content_directory"] = str(final)
        evidence["repository_bytes"] = tree_size(final / "repository.git")
        if analysis is None:
            return None, reason, evidence
        projection = {
            **analysis,
            "content_directory": str(final),
            "repository_git_directory": str(final / "repository.git"),
            "repository_bytes": evidence["repository_bytes"],
            "fixed_commit_sha": fixed,
            "parent_commit_sha": parent,
        }
        return projection, "selected", evidence
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def validate_git_checkpoint(
    checkpoint: Mapping[str, Any], common: Mapping[str, Any], config: Mapping[str, Any]
) -> None:
    for key, value in common.items():
        require(checkpoint.get(key) == value, f"Git checkpoint binding changed: {key}")
    require(isinstance(checkpoint.get("accepted"), bool), "Git checkpoint accepted invalid")
    require(isinstance(checkpoint.get("reason"), str), "Git checkpoint reason invalid")
    projection = checkpoint.get("projection")
    require(
        (checkpoint["accepted"] and isinstance(projection, dict))
        or (not checkpoint["accepted"] and projection is None),
        "Git checkpoint projection mismatch",
    )
    if checkpoint["accepted"]:
        git_dir = Path(projection["repository_git_directory"])
        require(git_dir.is_dir(), "cached repository missing")
        require(
            object_exists(config, git_dir, projection["fixed_commit_sha"] + "^{commit}"),
            "cached fixed commit missing",
        )
        require(
            object_exists(config, git_dir, projection["parent_commit_sha"] + "^{commit}"),
            "cached parent commit missing",
        )


def process_candidate(
    config: Mapping[str, Any],
    candidate: dict[str, Any],
    client: GitHubClient,
    common_base: Mapping[str, Any],
    counters: Counter[str],
    consumed_api: set[Path],
    consumed_git: set[Path],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    output = Path(config["output_directory"])
    candidate_id = candidate["candidate_id"]
    common = {**common_base, "candidate_id": candidate_id}
    full_name = candidate["pr"]["repository_full_name"]
    pr_number = candidate["pr"]["pr_number"]

    def request(
        stage: str,
        url: str,
        projector: Callable[[Any], tuple[dict[str, Any] | None, str]],
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = output / "checkpoints" / stage / f"{candidate_id}.json"
        result, cached = checkpointed_request(
            path,
            common={**common, "stage": stage, **(extra or {})},
            url=url,
            client=client,
            projector=projector,
        )
        consumed_api.add(path)
        counters["api_cached" if cached else "api_logical"] += 1
        return result

    def rejected(stage: str, reason: str) -> tuple[dict[str, Any], None]:
        return {
            "feasibility_order": candidate["feasibility_order"],
            "candidate_id": candidate_id,
            "projected_split": candidate["projected_split"],
            "selection_stratum": candidate["selection_stratum"],
            "repository_split_group": candidate["repository_split_group"],
            "state": "rejected",
            "terminal_stage": stage,
            "reason": reason,
            "replacement_allowed": False,
        }, None

    merge_sha = candidate["pr"]["merge_commit_sha"]
    head_sha = candidate["pr"]["head_sha"]
    commit = request(
        "commit",
        f"/repos/{full_name}/commits/{merge_sha}",
        lambda document: project_commit(document, merge_sha, head_sha),
    )
    if not commit["accepted"]:
        return rejected("commit", commit["reason"])
    commit_projection = commit["projection"]

    pr_commits = request(
        "pr-commits",
        f"/repos/{full_name}/pulls/{pr_number}/commits?per_page=100",
        lambda document: project_pr_commits(document, head_sha, 100),
    )
    if not pr_commits["accepted"]:
        return rejected("pr-commits", pr_commits["reason"])

    pr_files = request(
        "pr-files",
        f"/repos/{full_name}/pulls/{pr_number}/files?per_page=100",
        lambda document: project_pr_files(
            document, candidate["pr"]["changed_files"], 100
        ),
    )
    if not pr_files["accepted"]:
        return rejected("pr-files", pr_files["reason"])

    allowed_spdx = set(config["license"]["allowed_spdx"])
    licenses: dict[str, dict[str, Any]] = {}
    for role, ref in (
        ("parent", commit_projection["parent_commit_sha"]),
        ("fixed", commit_projection["fixed_commit_sha"]),
    ):
        license_result = request(
            "license-" + role,
            f"/repos/{full_name}/license?ref={quote(ref, safe='')}",
            lambda document: project_license(document, allowed_spdx),
            {"ref": ref, "commit_role": role},
        )
        if not license_result["accepted"]:
            return rejected("license-" + role, license_result["reason"])
        licenses[role] = license_result["projection"]

    git_checkpoint_path = output / "checkpoints" / "git" / f"{candidate_id}.json"
    git_common = {**common, "stage": "git"}
    if git_checkpoint_path.exists():
        git_checkpoint = load_json(git_checkpoint_path)
        validate_git_checkpoint(git_checkpoint, git_common, config)
        counters["git_cached"] += 1
    else:
        projection, reason, evidence = prepare_git_content(
            config, candidate, commit_projection, pr_files["projection"]
        )
        counters["git_fetches"] += 1
        git_checkpoint = {
            **git_common,
            "accepted": projection is not None,
            "reason": reason,
            "projection": projection,
            "evidence": evidence,
        }
        write_json_atomic(git_checkpoint_path, git_checkpoint)
    consumed_git.add(git_checkpoint_path)
    if not git_checkpoint["accepted"]:
        return rejected("git", git_checkpoint["reason"])

    plan = {
        **candidate,
        "commit_pair": commit_projection,
        "pr_commits": pr_commits["projection"],
        "pr_files": pr_files["projection"],
        "historical_license": licenses,
        "static_content": git_checkpoint["projection"],
        "execution_profile": "cmake_ctest_out_of_tree_v1",
        "execution_pending": True,
        "training_admitted": False,
    }
    decision = {
        "feasibility_order": candidate["feasibility_order"],
        "candidate_id": candidate_id,
        "projected_split": candidate["projected_split"],
        "selection_stratum": candidate["selection_stratum"],
        "repository_split_group": candidate["repository_split_group"],
        "state": "execution_candidate",
        "terminal_stage": "static-content",
        "reason": "selected",
        "replacement_allowed": False,
    }
    return decision, plan


def write_final_outputs(
    config: Mapping[str, Any],
    config_path: Path,
    plans: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    summary: dict[str, Any],
    counters: Mapping[str, int],
    client: GitHubClient,
) -> None:
    output = Path(config["output_directory"])
    final_names = ("content-plan.jsonl", "decisions.jsonl", "summary.json", "run-manifest.json")
    require(not any((output / name).exists() for name in final_names), "refusing to overwrite final content outputs")
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "content-plan.jsonl": jsonl_bytes(plans),
        "decisions.jsonl": jsonl_bytes(decisions),
        "summary.json": json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    }
    for name, payload in payloads.items():
        temporary = output / (name + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(output / name)
    manifest = {
        "version": VERSION,
        "git_commit": current_commit(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256_file(config_path),
        "script_sha256": sha256_file(Path(__file__)),
        "selection_manifest_sha256": config["selection"]["run_manifest"]["sha256"],
        "authenticated_github_api": client.authenticated,
        "network_attempts": client.actual_requests,
        "request_and_fetch_counts": dict(sorted(counters.items())),
        "content_boundaries": config["scope"],
        "outputs": {
            name: {"sha256": sha256_bytes(payload)} for name, payload in payloads.items()
        },
    }
    write_json_atomic(output / "run-manifest.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)
    validate_config(config)
    selected = read_jsonl(Path(config["selection"]["candidates"]["path"]))
    validate_selection(selected)
    git_binary = Path(config["git"]["binary"])
    require(git_binary.is_file() and os.access(git_binary, os.X_OK), "Git missing")
    require(sha256_file(git_binary) == config["git"]["sha256"], "Git binary hash changed")
    version = subprocess.check_output([str(git_binary), "--version"], text=True).strip()
    require(version == config["git"]["version"], "Git runtime version changed")
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "version": VERSION,
                    "mode": "preflight-only",
                    "fixed_denominator": len(selected),
                    "unique_repositories": len(
                        {row["repository_split_group"] for row in selected}
                    ),
                    "git_version": version,
                    "network_requests": 0,
                    "content_writes": 0,
                    "untrusted_build_executed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    output = Path(config["output_directory"])
    final_names = ("content-plan.jsonl", "decisions.jsonl", "summary.json", "run-manifest.json")
    require(not any((output / name).exists() for name in final_names), "final content output already exists")
    output.mkdir(parents=True, exist_ok=True)
    Path(config["content_root"]).mkdir(parents=True, exist_ok=True)
    client = GitHubClient(config["api"])
    common_base = {
        "version": VERSION,
        "config_sha256": sha256_file(args.config),
        "script_sha256": sha256_file(Path(__file__)),
        "git_commit": current_commit(),
        "selection_sha256": config["selection"]["candidates"]["sha256"],
    }
    counters: Counter[str] = Counter()
    consumed_api: set[Path] = set()
    consumed_git: set[Path] = set()
    decisions: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        decision, plan = process_candidate(
            config,
            candidate,
            client,
            common_base,
            counters,
            consumed_api,
            consumed_git,
        )
        decisions.append(decision)
        if plan is not None:
            plans.append(plan)
        print(
            json.dumps(
                {
                    "candidate": index,
                    "total": len(selected),
                    "state": decision["state"],
                    "stage": decision["terminal_stage"],
                    "reason": decision["reason"],
                    "execution_candidates": len(plans),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        total_bytes = sum(
            row["static_content"]["repository_bytes"] for row in plans
        ) + sum(
            checkpoint.get("evidence", {}).get("repository_bytes", 0)
            for path in consumed_git
            for checkpoint in [load_json(path)]
            if not checkpoint["accepted"]
        )
        require(
            total_bytes <= config["git"]["maximum_total_repository_bytes"],
            "total repository byte limit exceeded",
        )
    require(counters["api_logical"] <= config["api"]["maximum_logical_requests"], "API logical budget exceeded")
    require(counters["git_fetches"] <= config["git"]["maximum_fetches"], "Git fetch budget exceeded")
    all_api = {
        path
        for stage in (
            "commit",
            "pr-commits",
            "pr-files",
            "license-parent",
            "license-fixed",
        )
        for path in (output / "checkpoints" / stage).glob("*.json")
    }
    all_git = set((output / "checkpoints" / "git").glob("*.json"))
    require(consumed_api == all_api, "API checkpoint tree contains unexpected entries")
    require(consumed_git == all_git, "Git checkpoint tree contains unexpected entries")
    rejection_counts = Counter(
        f'{row["terminal_stage"]}:{row["reason"]}'
        for row in decisions
        if row["state"] == "rejected"
    )
    split_counts = Counter(row["projected_split"] for row in plans)
    label_counts = Counter(row["selection_stratum"] for row in plans)
    static_reachable = len(plans) >= 4
    summary = {
        "version": VERSION,
        "fixed_denominator": len(selected),
        "execution_candidates": len(plans),
        "execution_candidate_split_counts": {
            split: split_counts[split] for split in ("train", "validation")
        },
        "execution_candidate_label_strata": {
            stratum: label_counts[stratum] for stratum in ("bug_label", "no_bug_label")
        },
        "rejections": dict(sorted(rejection_counts.items())),
        "minimum_executable_records": 4,
        "execution_gate_still_reachable": static_reachable,
        "offline_execution_array_authorized": static_reachable,
        "untrusted_build_executed": False,
        "training_admitted": False,
        "gpu_used": False,
    }
    write_final_outputs(config, args.config, plans, decisions, summary, counters, client)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
