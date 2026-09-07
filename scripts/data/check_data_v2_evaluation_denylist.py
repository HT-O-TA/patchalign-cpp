#!/usr/bin/env python3
"""Validate and compile the Data-v2 evaluation identity denylist."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from scripts.data.check_data_v2_contract import canonical_repository, validate_contract


VERSION = "data-v2-evaluation-denylist-v1"
DEFAULT_CONFIG = Path("configs/data/data_v2_evaluation_denylist_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_identity_set(values: set[str]) -> str:
    return sha256_bytes("".join(value + "\n" for value in sorted(values)).encode("utf-8"))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_bound_file(spec: dict[str, Any], label: str) -> dict[str, Any]:
    path = Path(spec["path"])
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return load_json(path) if path.suffix == ".json" else {}


def normalize_repository_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def validate_static_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected denylist version")
    verify_bound_file(config["decision"], "ADR-0014")
    contract = verify_bound_file(config["contract"], "Data-v2 contract")
    validate_contract(contract)
    source_admission = verify_bound_file(config["source_admission"], "source admission registry")
    require(source_admission["version"] == "data-v2-source-admission-v1", "wrong source registry")
    require(
        config["scope"]
        == {
            "complete_for_candidate_content_acquisition": True,
            "future_evaluation_additions_invalidate_completeness": True,
            "exact_content_and_commit_dedup_still_required": True,
            "training_admitted": False,
            "gpu_authorized": False,
            "dpo_authorized": False,
            "evaluation_gold_consumed": False,
        },
        "scope changed",
    )
    manifests = config["frozen_manifests"]
    require(set(manifests) == {"formal_holdout", "confirmation", "defects4c"}, "manifest inventory changed")
    require(
        (manifests["formal_holdout"]["case_count"], manifests["confirmation"]["case_count"], manifests["defects4c"]["case_count"])
        == (500, 124, 176),
        "evaluation case counts changed",
    )
    require(manifests["formal_holdout"]["identity_field"] == "problem_id", "formal identity changed")
    require(manifests["confirmation"]["identity_field"] == "problem_id", "confirmation identity changed")
    require(manifests["defects4c"]["identity_field"] == "project", "external identity changed")
    require(manifests["formal_holdout"]["unique_identity_count"] == 500, "formal family count changed")
    require(manifests["confirmation"]["unique_identity_count"] == 124, "confirmation family count changed")
    require(len(manifests["defects4c"]["expected_unique_identities"]) == 6, "external project count changed")

    benchmarks = config["protected_benchmarks"]
    require(set(benchmarks) == {"multi_swe_bench_cpp", "bugscpp", "llvm_apr", "debugbench"}, "benchmark inventory changed")
    require(benchmarks["multi_swe_bench_cpp"]["identity_revision"] == "9777648932daa214ba18c70c81e85821b5836f32", "Multi-SWE identity changed")
    require(len(benchmarks["multi_swe_bench_cpp"]["repositories"]) == 9, "Multi-SWE repository count changed")
    require(benchmarks["bugscpp"]["revision"] == "be5cc489cb2b3127ec3b73cb4adfdd290807f55b", "BugsCpp revision changed")
    require(benchmarks["bugscpp"]["published_defect_count"] == 215, "BugsCpp defect count changed")
    require(len(benchmarks["bugscpp"]["project_ids"]) == 24, "BugsCpp project count changed")
    require(benchmarks["llvm_apr"]["revision"] == "765534776d06d355b026f713f265653f34d8b3ad", "LLVM APR revision changed")
    require(benchmarks["debugbench"]["revision"] == "2761bab93c4c65351b19d0ef4a94b26abe47a185", "DebugBench revision changed")

    matching = config["repository_matching"]
    require(matching["normalize_repository_name_by_removing_non_alphanumeric"] is True, "normalization disabled")
    require(matching["fork_source_and_parent_resolution_required"] is True, "fork lineage requirement disabled")
    require(matching["exclude_if_any_normalized_component_contains"] == ["leetcode"], "DebugBench domain rule changed")
    exact = matching["exact_canonical_repositories"]
    require(exact == sorted(set(exact)), "exact repository list must be sorted and unique")
    require(all(canonical_repository(value) == value for value in exact), "non-canonical exact repository")
    required_exact = set(benchmarks["multi_swe_bench_cpp"]["repositories"])
    required_exact.update(
        {
            benchmarks["bugscpp"]["repository"],
            benchmarks["llvm_apr"]["repository"],
            benchmarks["llvm_apr"]["migrated_repository"],
            benchmarks["llvm_apr"]["underlying_repository"],
            benchmarks["debugbench"]["repository"],
        }
    )
    required_exact.update(
        "github.com/" + value.replace("___", "/")
        for value in manifests["defects4c"]["expected_unique_identities"]
    )
    require(required_exact <= set(exact), "a protected canonical repository is absent")
    aliases = matching["normalized_repository_name_aliases"]
    require(aliases == sorted(set(aliases)), "repository aliases must be sorted and unique")
    alias_norms = {normalize_repository_name(value) for value in aliases}
    require(len(alias_norms) == len(aliases), "repository aliases collide after normalization")
    require(
        {normalize_repository_name(value) for value in benchmarks["bugscpp"]["project_ids"]} <= alias_norms,
        "a BugsCpp project alias is absent",
    )
    require(config["output_directory"] == "artifacts/data-v2/evaluation-denylist-v1", "output path changed")


def repository_denial_reason(
    repository: str,
    config: dict[str, Any],
    *,
    is_fork: bool = False,
    fork_source: str | None = None,
    fork_parent: str | None = None,
) -> str | None:
    matching = config["repository_matching"]
    candidates = [canonical_repository(repository)]
    if is_fork:
        if not fork_source and not fork_parent:
            return "fork_lineage_unresolved"
        candidates.extend(canonical_repository(value) for value in (fork_source, fork_parent) if value)
    exact = set(matching["exact_canonical_repositories"])
    aliases = {normalize_repository_name(value) for value in matching["normalized_repository_name_aliases"]}
    block_tokens = set(matching["exclude_if_any_normalized_component_contains"])
    for candidate in candidates:
        if candidate in exact:
            return "exact_protected_repository"
        components = [normalize_repository_name(value) for value in candidate.split("/")]
        if components[-1] in aliases:
            return "protected_repository_alias"
        if any(token in component for token in block_tokens for component in components):
            return "protected_source_domain"
    return None


def compile_identity_sets(config: dict[str, Any]) -> dict[str, Any]:
    compiled: dict[str, set[str]] = {}
    for name, spec in config["frozen_manifests"].items():
        manifest = verify_bound_file(spec, f"{name} manifest")
        cases = manifest.get("cases")
        require(isinstance(cases, list), f"{name} cases missing")
        require(len(cases) == spec["case_count"], f"{name} case count changed")
        identities = {str(row[spec["identity_field"]]) for row in cases}
        if "unique_identity_count" in spec:
            require(len(identities) == spec["unique_identity_count"], f"{name} identity count changed")
            require(sha256_identity_set(identities) == spec["identity_set_sha256_lf"], f"{name} identity set changed")
        else:
            require(identities == set(spec["expected_unique_identities"]), f"{name} project set changed")
        compiled[name] = identities
    require(not (compiled["formal_holdout"] & compiled["confirmation"]), "formal/confirmation problem overlap")
    return {
        "problem_family_sets": {
            "formal_holdout": {
                "count": len(compiled["formal_holdout"]),
                "sha256_lf": sha256_identity_set(compiled["formal_holdout"]),
            },
            "confirmation": {
                "count": len(compiled["confirmation"]),
                "sha256_lf": sha256_identity_set(compiled["confirmation"]),
            },
            "overlap": 0,
            "union_count": len(compiled["formal_holdout"] | compiled["confirmation"]),
        },
        "external_projects": sorted(compiled["defects4c"]),
        "exact_canonical_repositories": config["repository_matching"]["exact_canonical_repositories"],
        "normalized_repository_name_aliases": config["repository_matching"]["normalized_repository_name_aliases"],
        "complete_for_candidate_content_acquisition": True,
        "training_admitted": False,
        "evaluation_gold_consumed": False,
    }


def current_commit() -> str:
    commit = os.environ.get("PATCHALIGN_GIT_COMMIT", "").strip() or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid Git commit")
    return commit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)
    validate_static_config(config)
    if args.static_only:
        print(json.dumps({"version": VERSION, "static_valid": True}, sort_keys=True))
        return
    output = Path(config["output_directory"])
    summary_path = output / "compiled-identities.json"
    manifest_path = output / "run-manifest.json"
    require(not summary_path.exists() and not manifest_path.exists(), "refusing to overwrite denylist outputs")
    summary = compile_identity_sets(config)
    write_json_atomic(summary_path, summary)
    manifest = {
        "version": VERSION,
        "git_commit": current_commit(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256_file(args.config),
        "script_sha256": sha256_file(Path(__file__)),
        "decision_sha256": config["decision"]["sha256"],
        "input_manifest_sha256": {
            name: spec["sha256"] for name, spec in sorted(config["frozen_manifests"].items())
        },
        "content_boundaries": {
            "identity_fields_consumed": ["problem_id", "project"],
            "prompt_or_code_emitted": False,
            "reference_patch_or_test_emitted": False,
            "evaluation_gold_consumed": False,
        },
        "outputs": {
            "compiled-identities.json": {"sha256": sha256_file(summary_path)},
        },
    }
    write_json_atomic(manifest_path, manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
