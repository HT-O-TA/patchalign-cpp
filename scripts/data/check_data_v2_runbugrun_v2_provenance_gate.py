#!/usr/bin/env python3
"""Fail-closed validator for the RunBugRun v2 Data-v2 provenance gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VERSION = "data-v2-runbugrun-v2-provenance-gate-v1"
DEFAULT_CONFIG = Path("configs/data/data_v2_runbugrun_v2_provenance_gate_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected provenance gate version")
    source = config["source"]
    require(source["id"] == "runbugrun-v2", "source identity changed")
    require(source["tag"] == "v2", "source tag changed")
    require(source["revision"] == "bbac70b7ae7331d87892e861356cf133476bc938", "source revision changed")
    require(source["release_asset"] == {"name": "runbugrun.sql.lrz", "size_bytes": 120501798}, "release asset changed")

    decision = config["decision"]
    require(decision["metadata_and_schema_research_authorized"] is True, "metadata research disabled")
    for key in (
        "full_release_download_authorized",
        "program_or_test_content_acquisition_authorized",
        "data_v2_training_admission_authorized",
        "sft_authorized",
        "dpo_authorized",
        "redistribution_authorized",
        "gpu_required",
    ):
        require(decision[key] is False, f"fail-closed boundary weakened: {key}")

    reason = config["reason"]
    require(reason["repository_or_dataset_license_is_not_per_record_clearance"] is True, "license boundary removed")
    require(reason["upstream_submitter_rights_and_ai_training_consent_are_not_resolved_per_record"] is True, "provenance uncertainty removed")
    require(reason["historical_terms_are_not_inferred_from_current_terms"] is True, "historical inference enabled")
    require(reason["legal_advice_claimed"] is False, "legal advice claim changed")

    require(
        set(config["reconsideration_requires"])
        == {
            "per_record_origin_platform_and_identity",
            "applicable_training_and_redistribution_authorization",
            "exclusion_of_unknown_or_opted_out_content",
            "evaluation_contamination_audit",
            "new_versioned_ADR_and_machine_contract",
        },
        "reconsideration requirements changed",
    )
    require(len(config["official_evidence_urls"]) >= 5, "official evidence inventory incomplete")
    require(config["historical_experiments"]["facts_rewritten"] is False, "historical facts rewritten")
    require(config["historical_experiments"]["external_release_requires_source_limit_disclosure"] is True, "release disclosure disabled")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    validate(json.loads(args.config.read_text(encoding="utf-8")))
    print(json.dumps({"valid": True, "version": VERSION}, sort_keys=True))


if __name__ == "__main__":
    main()

