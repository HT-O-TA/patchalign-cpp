#!/usr/bin/env python3
"""Audit preregistered BugsCpp projects and current repository license metadata."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from scripts.data.audit_data_v2_commitpack_shard import stable_hash


VERSION = "data-v2-bugscpp-project-license-probe-v1"
SHA_RE = re.compile(r"[0-9a-f]{40}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def canonical_repository_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    parts = [part for part in parsed.path.rstrip("/").split("/") if part]
    if len(parts) < 2:
        return None
    repository = parts[-1].removesuffix(".git")
    owner = parts[-2]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        return None
    return f"{parsed.netloc.casefold()}/{owner.casefold()}/{repository.casefold()}"


def expected_split(registry: list[Mapping[str, Any]], seed: int) -> dict[str, str]:
    candidates = [row for row in registry if row["split"] != "excluded"]
    ordered = sorted(candidates, key=lambda row: stable_hash(seed, row["id"]))
    total = sum(int(row["defects"]) for row in candidates)
    result: dict[str, str] = {}
    heldout_count = 0
    heldout_projects = 0
    cursor = 0
    while cursor < len(ordered) and (heldout_projects < 4 or heldout_count < math.ceil(total * 0.20)):
        row = ordered[cursor]
        result[str(row["id"])] = "heldout"
        heldout_count += int(row["defects"])
        heldout_projects += 1
        cursor += 1
    validation_count = 0
    validation_projects = 0
    while cursor < len(ordered) and (validation_projects < 3 or validation_count < math.ceil(total * 0.15)):
        row = ordered[cursor]
        result[str(row["id"])] = "validation"
        validation_count += int(row["defects"])
        validation_projects += 1
        cursor += 1
    for row in ordered[cursor:]:
        result[str(row["id"])] = "train"
    return result


def verify_config(config: Mapping[str, Any], require_repo: bool) -> None:
    require(config.get("version") == VERSION, "unexpected config version")
    for label in ("decision", "evaluation_denylist"):
        spec = config[label]
        path = Path(str(spec["path"]))
        require(path.is_file(), f"missing {label}: {path}")
        require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    scope = config["scope"]
    require(scope["project_split_frozen_before_patch_read"] is True, "split is not frozen")
    require(scope["metadata_only"] is True, "metadata-only boundary changed")
    for key in (
        "patch_blob_read", "source_or_test_download_authorized", "upstream_program_execution",
        "heldout_license_request_authorized", "training_data_created", "gpu_authorized",
        "dpo_authorized", "evaluation_gold_consumed",
    ):
        require(scope[key] is False, f"unsafe scope flag enabled: {key}")
    policy = config["split_policy"]
    require(policy["patch_or_test_signal_used"] is False, "patch/test signal used for split")
    require(policy["resplit_after_results_allowed"] is False, "resplit enabled")
    registry = config["project_registry"]
    require(len(registry) == 24, "project registry size changed")
    require(len({row["id"] for row in registry}) == 24, "duplicate project id")
    require(sum(int(row["defects"]) for row in registry) == 215, "defect total changed")
    computed = expected_split(registry, int(policy["seed"]))
    for row in registry:
        if row["split"] != "excluded":
            require(computed[row["id"]] == row["split"], f"preregistered split changed: {row['id']}")
    excluded = {row["id"]: row.get("exclude_reason") for row in registry if row["split"] == "excluded"}
    require(excluded == {
        "cppcheck": "current_defects4c_repository_overlap",
        "example": "benchmark_example_not_real_project",
    }, "excluded project set changed")
    requests = {
        canonical_repository_url(row["url"])
        for row in registry
        if row["split"] in {"train", "validation"}
        and canonical_repository_url(row["url"])
        and canonical_repository_url(row["url"]).startswith("github.com/")
    }
    require(len(requests) <= int(config["license_probe"]["maximum_requests"]), "request budget exceeded")
    if require_repo:
        repo = Path(str(config["upstream"]["partial_clone_path"]))
        require((repo / "HEAD").is_file() or (repo / ".git").is_dir(), "partial clone missing")
        completed = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{config['upstream']['revision']}^{{commit}}"],
            check=False,
        )
        require(completed.returncode == 0, "frozen BugsCpp revision missing")


def git_show(repo: Path, revision: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{path}"],
        check=False, capture_output=True,
    )
    require(completed.returncode == 0, f"cannot read frozen metadata: {path}")
    return completed.stdout


def read_metadata(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    repo = Path(str(config["upstream"]["partial_clone_path"]))
    revision = str(config["upstream"]["revision"])
    result: dict[str, dict[str, Any]] = {}
    for expected in config["project_registry"]:
        project_id = str(expected["id"])
        path = str(config["upstream"]["metadata_path_template"]).format(project_id=project_id)
        raw = git_show(repo, revision, path)
        metadata = json.loads(raw)
        require(isinstance(metadata, dict), f"invalid metadata object: {project_id}")
        require(canonical_repository_url(metadata["info"]["url"]) == canonical_repository_url(expected["url"]), f"URL changed: {project_id}")
        defects = metadata.get("defects")
        require(isinstance(defects, list) and len(defects) == int(expected["defects"]), f"defect count changed: {project_id}")
        ids = [item.get("id") for item in defects]
        require(ids == list(range(1, len(defects) + 1)), f"defect IDs changed: {project_id}")
        commits = [item.get("hash") for item in defects]
        require(all(isinstance(value, str) and SHA_RE.fullmatch(value) for value in commits), f"base commit invalid: {project_id}")
        result[project_id] = {
            "metadata_sha256": sha256_bytes(raw),
            "base_commit_count": len(set(commits)),
            "base_commit_set_sha256_lf": sha256_bytes("".join(f"{value}\n" for value in sorted(set(commits))).encode("utf-8")),
        }
    return result


def request_repository_metadata(endpoint: str, repository: str, retries: int = 4) -> tuple[dict[str, Any], str]:
    _, owner, name = repository.split("/", 2)
    url = endpoint.format(owner=owner, repository=name)
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "patchalign-cpp-source-audit-v1"})
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=45) as response:
                raw = response.read()
            value = json.loads(raw)
            require(isinstance(value, dict), f"non-object repository metadata: {repository}")
            require(str(value.get("full_name", "")).casefold() == f"{owner}/{name}", f"repository identity changed: {repository}")
            return value, sha256_bytes(raw)
        except (HTTPError, URLError, TimeoutError) as error:
            if attempt + 1 == retries:
                raise RuntimeError(f"GitHub repository metadata failed: {repository}: {error}") from error
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def audit(config: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = read_metadata(config)
    license_config = config["license_probe"]
    allowed = set(license_config["allowed_spdx"])
    endpoint = str(license_config["github_repository_metadata_endpoint"])
    cache: dict[str, dict[str, Any]] = {}
    request_count = 0
    results: list[dict[str, Any]] = []
    last_request = 0.0
    for project in config["project_registry"]:
        project_id = str(project["id"])
        split = str(project["split"])
        repository = canonical_repository_url(project["url"])
        assert repository is not None
        state = "not_eligible"
        spdx: str | None = None
        response_hash: str | None = None
        if split == "heldout":
            state = "heldout_unqueried"
        elif split in {"train", "validation"}:
            if not repository.startswith("github.com/"):
                state = "unsupported_host"
            else:
                if repository not in cache:
                    remaining = float(license_config["minimum_seconds_between_requests"]) - (time.monotonic() - last_request)
                    if remaining > 0:
                        time.sleep(remaining)
                    value, response_hash = request_repository_metadata(endpoint, repository)
                    last_request = time.monotonic()
                    request_count += 1
                    license_value = value.get("license")
                    spdx = license_value.get("spdx_id") if isinstance(license_value, dict) else None
                    cache[repository] = {
                        "spdx": spdx,
                        "response_sha256": response_hash,
                        "archived": bool(value.get("archived")),
                        "fork": bool(value.get("fork")),
                    }
                entry = cache[repository]
                spdx = entry["spdx"]
                response_hash = entry["response_sha256"]
                state = "allowlisted_current_license" if spdx in allowed else "current_license_not_allowlisted"
        result = {
            "project_id": project_id,
            "split": split,
            "defects": int(project["defects"]),
            "repository_identity_sha256": sha256_bytes(repository.encode("utf-8")),
            "metadata_sha256": metadata[project_id]["metadata_sha256"],
            "base_commit_count": metadata[project_id]["base_commit_count"],
            "base_commit_set_sha256_lf": metadata[project_id]["base_commit_set_sha256_lf"],
            "license_state": state,
            "current_spdx": spdx,
            "repository_response_sha256": response_hash,
        }
        results.append(result)
    require(request_count <= int(license_config["maximum_requests"]), "request budget exceeded at runtime")

    split_summary: dict[str, Any] = {}
    for split in ("train", "validation", "heldout", "excluded"):
        rows = [row for row in results if row["split"] == split]
        allowed_rows = [row for row in rows if row["license_state"] == "allowlisted_current_license"]
        split_summary[split] = {
            "projects": len(rows),
            "defects": sum(row["defects"] for row in rows),
            "allowlisted_current_license_projects": len(allowed_rows),
            "allowlisted_current_license_defects": sum(row["defects"] for row in allowed_rows),
            "license_states": dict(sorted(Counter(row["license_state"] for row in rows).items())),
        }
    gates: dict[str, Any] = {}
    for split in ("train", "validation"):
        target = config["upper_bound_gate"][split]
        actual = {
            "allowlisted_current_license_defects": split_summary[split]["allowlisted_current_license_defects"],
            "allowlisted_projects": split_summary[split]["allowlisted_current_license_projects"],
        }
        checks = {key: actual[key] >= int(value) for key, value in target.items()}
        gates[split] = {"actual": actual, "target": target, "checks": checks, "all_passed": all(checks.values())}
    all_passed = gates["train"]["all_passed"] and gates["validation"]["all_passed"]
    summary = {
        "version": VERSION,
        "status": "project_and_current_license_metadata_only",
        "project_split": split_summary,
        "github_requests": request_count,
        "upper_bound_gate": {"train": gates["train"], "validation": gates["validation"], "all_passed": all_passed},
        "decision": {
            "patch_header_and_historical_license_audit_authorized": all_passed,
            "patch_or_source_download_authorized": False,
            "training_authorized": False,
            "gpu_authorized": False,
            "next_action": "freeze patch-header and historical-license audit" if all_passed else "close BugsCpp training route without resplit",
        },
        "interpretation_boundary": [
            "Project split was frozen before any patch blob was read.",
            "Current repository SPDX is an upper-bound signal, not historical license clearance.",
            "Held-out project licenses and all patch, source, tests, descriptions, and execution results were not requested or emitted.",
            "A pass authorizes only a versioned patch-header and historical-license audit.",
        ],
    }
    return summary, results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/data/data_v2_bugscpp_project_license_probe_v1.json"))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)
    verify_config(config, require_repo=not args.preflight_only)
    if args.preflight_only:
        print(json.dumps({"version": VERSION, "preflight": "passed"}, sort_keys=True))
        return
    output = Path(str(config["output_directory"]))
    require(not output.exists(), f"output already exists: {output}")
    summary, projects = audit(config)
    output.mkdir(parents=True)
    projects_path = output / "project-decisions.jsonl"
    projects_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in projects), encoding="utf-8", newline="\n")
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": os.environ.get("PATCHALIGN_GIT_COMMIT", "unknown"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", "local"),
        "config_sha256": sha256_file(args.config),
        "upstream_revision": config["upstream"]["revision"],
        "output_sha256": {
            "project-decisions.jsonl": sha256_file(projects_path),
            "summary.json": sha256_file(summary_path),
        },
    }
    (output / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
