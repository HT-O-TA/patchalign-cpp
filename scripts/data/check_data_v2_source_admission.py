#!/usr/bin/env python3
"""Validate the desk-research source registry without downloading source data."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


VERSION = "data-v2-source-admission-v1"
DECISIONS = {"metadata_pilot", "evaluation_reserve", "reject"}
DIMENSIONS = {
    "license",
    "availability",
    "real_fix_pair",
    "family_diversity",
    "long_and_multiline_supply",
    "executable_tests",
    "evaluation_contamination",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    require(registry.get("version") == VERSION, "unexpected registry version")
    require(set(registry.get("admission_dimensions", [])) == DIMENSIONS, "admission dimensions changed")

    state = registry["state"]
    require(state["desk_research_complete"] is True, "desk research is not complete")
    for key in ("content_downloaded", "training_data_frozen", "gpu_job_authorized"):
        require(state[key] is False, f"{key} must remain false")

    policy = registry["contamination_policy"]
    require(policy["evaluation_gold_consumed"] is False, "evaluation gold boundary changed")
    require(policy["exclude_entire_repository_for_frozen_or_reserved_repository_benchmarks"] is True, "repository exclusion disabled")
    require(policy["require_complete_repository_denylist_before_content_acquisition"] is True, "denylist gate disabled")

    family = registry["family_contract_blocker"]
    require(family["maximum_samples_per_family_across_v1_plus_increment"] == 2, "family cap changed")
    require(family["provisional_minimum_new_family_samples_train"] == 1600, "new-family target changed")
    expected_minimum = (family["provisional_minimum_new_family_samples_train"] + family["maximum_samples_per_family_across_v1_plus_increment"] - 1) // family["maximum_samples_per_family_across_v1_plus_increment"]
    require(family["minimum_unseen_repositories_if_repo_is_family"] == expected_minimum, "repository lower bound is inconsistent")
    require(family["decision_required"] is True, "family decision gate disabled")
    require(family["silent_relaxation_allowed"] is False, "silent family relaxation enabled")

    sources = registry["sources"]
    ids = [source["id"] for source in sources]
    require(len(ids) == len(set(ids)), "duplicate source id")
    require(registry["preferred_path"] in ids, "preferred source is missing")

    for source in sources:
        require(source["decision"] in DECISIONS, f"unexpected decision for {source['id']}")
        require(source["official_url"].startswith("https://"), f"non-HTTPS official URL for {source['id']}")
        require(source["primary_evidence_urls"], f"missing primary evidence for {source['id']}")
        require(all(url.startswith("https://") for url in source["primary_evidence_urls"]), f"non-HTTPS evidence for {source['id']}")
        require(source["content_download_authorized"] is False, f"content download authorized for {source['id']}")
        require(source["blockers"], f"missing blockers for {source['id']}")
        if source["decision"] == "reject":
            require(source["next_action"] == "none", f"rejected source has action: {source['id']}")
        else:
            require(source["next_action"] != "none", f"active source lacks action: {source['id']}")
        if source["decision"] == "evaluation_reserve":
            require("training" not in source["role"], f"evaluation reserve assigned training role: {source['id']}")

    reserves = {source["id"] for source in sources if source["decision"] == "evaluation_reserve"}
    require(set(policy["protected_benchmark_source_ids"]) == reserves, "protected benchmark set differs from reserves")

    counts = Counter(source["decision"] for source in sources)
    return {
        "version": VERSION,
        "source_count": len(sources),
        "decision_counts": dict(sorted(counts.items())),
        "preferred_path": registry["preferred_path"],
        "minimum_unseen_repositories_if_repo_is_family": family["minimum_unseen_repositories_if_repo_is_family"],
        "content_downloaded": False,
        "training_data_frozen": False,
        "gpu_job_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/data_v2_source_admission_v1.json"),
    )
    args = parser.parse_args()
    registry = json.loads(args.config.read_text(encoding="utf-8"))
    print(json.dumps(validate_registry(registry), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
