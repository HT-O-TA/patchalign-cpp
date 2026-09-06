#!/usr/bin/env python3
"""Validate the accepted hierarchical family contract for Data-v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


VERSION = "data-v2-contract-v2.1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_repository(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^git@([^:]+):", r"\1/", value)
    value = value.removesuffix(".git").strip("/")
    parts = [part for part in value.split("/") if part]
    require(len(parts) >= 3, f"repository identity lacks host/owner/repo: {value}")
    return "/".join(parts[-3:])


def assign_new_split(split_group: str, validation_percent: int, seed: int) -> str:
    payload = f"{seed}\0{split_group}".encode("utf-8")
    bucket = int(hashlib.sha256(payload).hexdigest()[:8], 16) % 100
    return "validation" if bucket < validation_percent else "train"


def repository_sampling_family(
    split_group: str,
    target_path: str,
    symbol_or_issue: str | None = None,
    hunk_anchor_hash: str | None = None,
) -> str:
    path = target_path.replace("\\", "/").strip("/").lower()
    require(path and ".." not in path.split("/"), "unsafe or empty target path")
    discriminator = (symbol_or_issue or "").strip().lower()
    if not discriminator:
        require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", hunk_anchor_hash or "")), "missing stable fallback anchor")
        discriminator = str(hunk_anchor_hash)
    return f"{split_group}|{path}|{discriminator}"


def validate_contract(config: dict[str, Any]) -> dict[str, Any]:
    require(config.get("version") == VERSION, "unexpected contract version")
    require(config.get("owner_accepted") is True, "owner acceptance missing")
    scope = config["scope"]
    require(scope["capacity_probe_only"] is True, "capacity-only boundary changed")
    for key in (
        "source_content_download_authorized",
        "training_dataset_freeze_authorized",
        "gpu_authorized",
        "a5_dpo_authorized",
    ):
        require(scope[key] is False, f"{key} must remain false")

    identity = config["identity"]
    require(identity["competitive_programming_source"]["synthetic_family_expansion_allowed"] is False, "synthetic family expansion enabled")
    required = set(identity["required_source_identity"])
    require({"repository_split_group", "sampling_family", "fix_commit_sha", "parent_commit_sha"} <= required, "source identity weakened")

    split = config["split"]
    require(split["existing_v1_mapping_wins"] is True, "existing split precedence changed")
    require(split["train_validation_repository_split_group_overlap"] == 0, "split overlap allowed")
    require(split["benchmark_repository_split_group_overlap"] == 0, "benchmark overlap allowed")
    require(split["new_split_group_validation_percent"] == 10, "validation split percent changed")

    caps = config["caps"]
    require(caps["maximum_samples_per_sampling_family_across_v1_plus_increment"] == 2, "sampling-family cap changed")
    require(caps["maximum_increment_samples_per_repository_split_group"] == {"train": 40, "validation": 20}, "repository cap changed")
    require(caps["maximum_single_new_source_fraction"] == 0.7, "source dominance cap changed")

    targets = config["provisional_increment"]
    expected = {
        "train": (2000, 100, 1000, 1200, 400),
        "validation": (200, 20, 100, 120, 40),
    }
    for split_name, values in expected.items():
        target = targets[split_name]
        observed = (
            target["total"],
            target["minimum_new_repository_split_groups"],
            target["minimum_new_sampling_families"],
            target["minimum_function"],
            target["minimum_file_window"],
        )
        require(observed == values, f"{split_name} core targets changed")
        repo_cap = caps["maximum_increment_samples_per_repository_split_group"][split_name]
        require(target["minimum_new_repository_split_groups"] * repo_cap >= target["total"], f"{split_name} repository target is mathematically infeasible")
        family_cap = caps["maximum_samples_per_sampling_family_across_v1_plus_increment"]
        require(target["minimum_new_sampling_families"] * family_cap >= target["total"], f"{split_name} sampling-family target is infeasible")
        require(target["minimum_function"] + target["minimum_file_window"] <= target["total"], f"{split_name} task-level minima exceed total")

    contamination = config["contamination"]
    require(contamination["evaluation_gold_consumed"] is False, "evaluation gold boundary changed")
    require(contamination["complete_reserved_repository_denylist_required_before_patch_download"] is True, "denylist gate disabled")
    require(config["reporting"]["metadata_pilot_is_training_admission"] is False, "metadata pilot promoted to training")
    return {
        "version": VERSION,
        "owner_accepted": True,
        "train_repository_minimum": targets["train"]["minimum_new_repository_split_groups"],
        "validation_repository_minimum": targets["validation"]["minimum_new_repository_split_groups"],
        "sampling_family_cap": caps["maximum_samples_per_sampling_family_across_v1_plus_increment"],
        "repository_caps": caps["maximum_increment_samples_per_repository_split_group"],
        "source_content_download_authorized": False,
        "gpu_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/data/data_v2_contract_v2_1.json"))
    args = parser.parse_args()
    value = json.loads(args.config.read_text(encoding="utf-8"))
    print(json.dumps(validate_contract(value), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
