#!/usr/bin/env python3
"""Complete fixed GitHub metadata with bug labels used only for stratification."""

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
import tempfile
from typing import Any, Mapping

from scripts.data.audit_data_v2_github_detail_early_stop import (
    canonical,
    checkpoint_inventory,
    validate_checkpoint,
)
from scripts.data.check_data_v2_contract import validate_contract
from scripts.data.collect_data_v2_github_detail_pilot import (
    GitHubClient,
    checkpointed_request,
    current_commit,
    jsonl_bytes,
    load_json,
    project_pr_detail,
    read_jsonl,
    sha256_bytes,
    sha256_file,
)
from scripts.data.collect_data_v2_github_metadata import has_bug_label


VERSION = "data-v2-github-executable-evidence-metadata-v2"
DEFAULT_CONFIG = Path(
    "configs/data/data_v2_github_executable_evidence_metadata_v2.json"
)
SOURCE_VERSION = "data-v2-github-detail-pilot-v1"
SOURCE_COMMIT = "bb30de8fb2327e53bd384d59baada235c56fd168"
SOURCE_CONFIG_SHA256 = (
    "sha256:0ff14154ffd8cf82ff4512b7f97f2125eab799bdbafe8de988202c200997a04d"
)
SOURCE_SCRIPT_SHA256 = (
    "sha256:85e2d553281a743d0c75fb3f78c3584716f27af4d88a1a77ac1741d8ed50770b"
)
SELECTION_SHA256 = (
    "sha256:a0cf60033dd42a60c64c5c62393b70a2f1f1509919114992ae551c401a776576"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_file(spec: Mapping[str, Any], label: str) -> Path:
    path = Path(str(spec["path"]))
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return path


def validate_config(config: Mapping[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected metadata v2 version")
    verify_file(config["decision"], "ADR-0021")
    contract = load_json(verify_file(config["contract"], "Data-v2 contract"))
    validate_contract(contract)
    denylist = load_json(
        verify_file(config["evaluation_denylist"], "evaluation denylist")
    )
    require(
        denylist["scope"]["complete_for_candidate_content_acquisition"] is True,
        "evaluation denylist incomplete",
    )
    source = config["source_v1"]
    require(source["version"] == SOURCE_VERSION, "source version changed")
    require(source["git_commit"] == SOURCE_COMMIT, "source commit changed")
    require(source["config_sha256"] == SOURCE_CONFIG_SHA256, "source config changed")
    require(source["script_sha256"] == SOURCE_SCRIPT_SHA256, "source script changed")
    require(source["selection"]["sha256"] == SELECTION_SHA256, "selection changed")
    require(source["selection"]["count"] == 200, "fixed denominator changed")
    require(
        source["selection"]["split_counts"] == {"train": 160, "validation": 40},
        "fixed split counts changed",
    )
    require(
        source["checkpoint_counts"] == {"pull": 145, "issue": 81, "license": 20},
        "source checkpoint counts changed",
    )
    audit = source["early_stop_audit"]
    require(audit["job_id"] == 97150, "source audit Job changed")
    for key in ("summary", "decisions", "checkpoint_inventory", "run_manifest"):
        verify_file(audit[key], f"source audit {key}")
    summary = load_json(Path(audit["summary"]["path"]))
    require(summary["completed_prefix"] == 144, "source completed prefix changed")
    require(summary["qualified_records"] == 8, "source qualified count changed")
    require(summary["outcome_gate_irrecoverable"] is True, "source gate changed")
    manifest = load_json(Path(audit["run_manifest"]["path"]))
    require(manifest["git_commit"] == "a169fdfc4ae09cd69d466e77c7aae4195d913d82", "audit commit changed")
    require(str(manifest["slurm_job_id"]) == "97150", "audit Job changed")
    require(
        manifest["checkpoint_inventory_sha256"]
        == audit["checkpoint_inventory"]["canonical_sha256"],
        "audit inventory reverse binding changed",
    )
    require(
        manifest["outputs"]["summary.json"]["sha256"]
        == audit["summary"]["sha256"],
        "audit summary reverse binding changed",
    )
    require(
        manifest["outputs"]["decisions.jsonl"]["sha256"]
        == audit["decisions"]["sha256"],
        "audit decisions reverse binding changed",
    )
    scope = {
        "metadata_only": True,
        "source_checkpoint_reuse": True,
        "patch_or_source_requested": False,
        "license_requested": False,
        "raw_response_stored": False,
        "text_or_user_identity_stored": False,
        "training_admitted": False,
        "gpu_authorized": False,
        "dpo_authorized": False,
    }
    require(config["scope"] == scope, "scope changed")
    gates = config["detail_gates"]
    require(gates["changed_files"] == {"minimum": 1, "maximum": 10}, "file gate changed")
    require(gates["changed_lines"] == {"minimum": 2, "maximum": 200}, "line gate changed")
    require(gates["require_same_repository_explicit_closing_issue"] is True, "closing issue gate changed")
    require(gates["require_closed_issue_not_pull_request"] is True, "closed issue gate changed")
    require(gates["bug_label_is_stratification_only"] is True, "label semantics changed")
    require(
        gates["linked_issue_bug_label_tokens"]
        == ["bug", "bugs", "bugfix", "defect", "defects"],
        "bug label tokens changed",
    )
    reuse = config["reuse_rules"]
    require(reuse["accepted_v1_pull_projection"] is True, "pull reuse disabled")
    require(reuse["accepted_v1_issue_projection"] is True, "issue reuse disabled")
    require(
        reuse["v1_no_bug_label_reason_implies_closed_issue_and_bug_label_false"]
        is True,
        "no-label inference changed",
    )
    require(
        reuse["all_other_v1_pull_or_issue_rejections_remain_terminal"] is True,
        "terminal rejection reuse changed",
    )
    require(reuse["v1_license_checkpoint_is_not_a_metadata_gate"] is True, "license semantics changed")
    api = config["api"]
    require(api["base_url"] == "https://api.github.com", "API base changed")
    require(api["maximum_attempts"] == 3, "retry policy changed")
    require(api["maximum_new_logical_requests"] == 111, "logical request budget changed")
    require(api["maximum_network_attempts_per_run"] == 117, "network request budget changed")
    require(api["unauthenticated_minimum_interval_seconds"] >= 61.0, "anonymous throttle weakened")
    require(api["authenticated_minimum_interval_seconds"] >= 0.5, "authenticated throttle weakened")
    require(
        config["outcome_gate"]
        == {
            "minimum_records": 50,
            "minimum_split_records": {"train": 40, "validation": 10},
            "minimum_split_repositories": {"train": 30, "validation": 8},
        },
        "outcome gate changed",
    )
    require(
        config["next_stage"]
        == {
            "fixed_feasibility_denominator": {"train": 16, "validation": 4},
            "minimum_executable_records": 4,
            "training_admitted": False,
        },
        "next-stage gate changed",
    )
    require(
        config["output_directory"]
        == "artifacts/data-v2/github-executable-evidence-v2/metadata",
        "output path changed",
    )


def project_issue_v2(
    number: int, document: dict[str, Any], config: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    if document.get("pull_request"):
        return None, "linked_reference_is_pull_request"
    if int(document.get("number") or 0) != number:
        return None, "linked_issue_identity_mismatch"
    if document.get("state") != "closed":
        return None, "linked_issue_not_closed"
    label_matched = has_bug_label(document, {"pilot": config["detail_gates"]})
    return {
        "number": number,
        "state": "closed",
        "bug_label_matched": label_matched,
    }, "selected"


def reuse_source_issue(
    checkpoint: Mapping[str, Any], issue_number: int
) -> tuple[dict[str, Any] | None, str]:
    if checkpoint["accepted"]:
        projection = checkpoint["projection"]
        require(projection["number"] == issue_number, "source issue number changed")
        require(projection["state"] == "closed", "source issue state changed")
        require(projection["bug_label_matched"] is True, "source issue label changed")
        return dict(projection), "selected"
    if checkpoint["reason"] == "linked_issue_without_bug_label":
        return {
            "number": issue_number,
            "state": "closed",
            "bug_label_matched": False,
        }, "selected"
    return None, str(checkpoint["reason"])


def load_and_validate_source(
    config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source = config["source_v1"]
    selected = read_jsonl(verify_file(source["selection"], "fixed selection"))
    decisions = read_jsonl(
        verify_file(source["early_stop_audit"]["decisions"], "source decisions")
    )
    require(len(selected) == 200 and len(decisions) == 200, "source denominator changed")
    expected_splits = ["train"] * 160 + ["validation"] * 40
    require([row["projected_split"] for row in selected] == expected_splits, "selection split order changed")
    require(
        [row["detail_pilot_order"] for row in selected] == list(range(200)),
        "selection order changed",
    )
    require(
        [row["candidate_id"] for row in selected]
        == [row["candidate_id"] for row in decisions],
        "audit decision order changed",
    )
    for candidate, decision in zip(selected, decisions, strict=True):
        require(candidate["projected_split"] == decision["projected_split"], "audit split changed")
        require(
            candidate["repository_split_group"] == decision["repository_split_group"],
            "audit repository changed",
        )
    inventory, inventory_sha = checkpoint_inventory(
        Path(source["checkpoint_root"]), source["checkpoint_counts"]
    )
    configured_inventory = json.loads(
        Path(source["early_stop_audit"]["checkpoint_inventory"]["path"]).read_text()
    )
    require(inventory == configured_inventory, "source checkpoint inventory changed")
    require(
        inventory_sha
        == source["early_stop_audit"]["checkpoint_inventory"]["canonical_sha256"],
        "source checkpoint inventory hash changed",
    )
    denylist = load_json(Path(config["evaluation_denylist"]["path"]))
    return selected, decisions, denylist


def source_common() -> dict[str, Any]:
    return {
        "version": SOURCE_VERSION,
        "config_sha256": SOURCE_CONFIG_SHA256,
        "script_sha256": SOURCE_SCRIPT_SHA256,
        "git_commit": SOURCE_COMMIT,
        "selection_sha256": SELECTION_SHA256,
    }


def write_final_outputs(
    config: Mapping[str, Any],
    config_path: Path,
    candidates: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    summary: dict[str, Any],
    manifest_facts: Mapping[str, Any],
) -> None:
    output = Path(config["output_directory"])
    final_names = ("candidate-metadata.jsonl", "decisions.jsonl", "summary.json", "run-manifest.json")
    require(not any((output / name).exists() for name in final_names), "refusing to overwrite final metadata v2 outputs")
    output.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="final-building-", dir=output))
    try:
        payloads = {
            "candidate-metadata.jsonl": jsonl_bytes(candidates),
            "decisions.jsonl": jsonl_bytes(decisions),
            "summary.json": json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        }
        for name, payload in payloads.items():
            (temporary / name).write_bytes(payload)
        manifest = {
            "version": VERSION,
            "git_commit": current_commit(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_sha256": sha256_file(config_path),
            "script_sha256": sha256_file(Path(__file__)),
            "source_audit_manifest_sha256": config["source_v1"]["early_stop_audit"]["run_manifest"]["sha256"],
            **manifest_facts,
            "content_boundaries": config["scope"],
            "outputs": {
                name: {"sha256": sha256_bytes(payload)}
                for name, payload in payloads.items()
            },
        }
        (temporary / "run-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for path in temporary.iterdir():
            path.replace(output / path.name)
        temporary.rmdir()
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def run(config: dict[str, Any], config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    selected, source_decisions, denylist = load_and_validate_source(config)
    output = Path(config["output_directory"])
    client = GitHubClient(config["api"])
    config_hash = sha256_file(config_path)
    script_hash = sha256_file(Path(__file__))
    commit = current_commit()
    new_common = {
        "version": VERSION,
        "config_sha256": config_hash,
        "script_sha256": script_hash,
        "git_commit": commit,
        "selection_sha256": SELECTION_SHA256,
    }
    old_common = source_common()
    source_root = Path(config["source_v1"]["checkpoint_root"])
    new_root = output / "checkpoints"
    consumed_new: set[Path] = set()
    logical_requests = 0
    source_reuses = Counter()
    rejections: Counter[str] = Counter()
    label_strata: Counter[str] = Counter()
    candidate_metadata: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    for index, (candidate, source_decision) in enumerate(
        zip(selected, source_decisions, strict=True), start=1
    ):
        candidate_id = candidate["candidate_id"]
        common = {**new_common, "candidate_id": candidate_id}
        pull_source = "v2_checkpoint"
        source_pull_path = source_root / "pull" / f"{candidate_id}.json"
        if source_pull_path.is_file():
            pull = load_json(source_pull_path)
            validate_checkpoint(
                pull,
                {**old_common, "candidate_id": candidate_id, "stage": "pull"},
                f"source pull/{candidate_id}",
            )
            pull_source = "v1_checkpoint"
            source_reuses["pull"] += 1
        else:
            require(source_decision["state"] == "unstarted", "missing source pull state changed")
            pull_path = new_root / "pull" / f"{candidate_id}.json"
            pull, cached = checkpointed_request(
                pull_path,
                common={**common, "stage": "pull"},
                url=candidate["pr_api_url"],
                client=client,
                projector=lambda document, row=candidate: project_pr_detail(
                    row, document, config, denylist
                ),
            )
            consumed_new.add(pull_path)
            logical_requests += int(not cached)
        if not pull["accepted"]:
            reason = "pull:" + pull["reason"]
            rejections[reason] += 1
            decisions.append(
                {
                    "detail_pilot_order": index - 1,
                    "candidate_id": candidate_id,
                    "projected_split": candidate["projected_split"],
                    "repository_split_group": candidate["repository_split_group"],
                    "state": "rejected",
                    "terminal_stage": "pull",
                    "reason": pull["reason"],
                    "pull_source": pull_source,
                }
            )
            print(json.dumps({"candidate": index, "stage": "pull", "reason": pull["reason"], "source": pull_source}, sort_keys=True), flush=True)
            continue

        detail = pull["projection"]
        issue_number = int(detail["linked_issue_number"])
        issue_source = "v2_checkpoint"
        source_issue_path = source_root / "issue" / f"{candidate_id}.json"
        if source_issue_path.is_file():
            issue = load_json(source_issue_path)
            validate_checkpoint(
                issue,
                {**old_common, "candidate_id": candidate_id, "stage": "issue"},
                f"source issue/{candidate_id}",
            )
            issue_projection, issue_reason = reuse_source_issue(issue, issue_number)
            issue_source = "v1_checkpoint"
            source_reuses["issue"] += 1
            issue_response_sha256 = issue["response"]["sha256"]
        else:
            require(
                source_decision["state"] in {"incomplete", "unstarted"},
                "missing source issue state changed",
            )
            issue_path = new_root / "issue" / f"{candidate_id}.json"
            issue, cached = checkpointed_request(
                issue_path,
                common={**common, "stage": "issue"},
                url=f'/repos/{detail["repository_full_name"]}/issues/{issue_number}',
                client=client,
                projector=lambda document, number=issue_number: project_issue_v2(
                    number, document, config
                ),
            )
            consumed_new.add(issue_path)
            logical_requests += int(not cached)
            issue_projection = issue["projection"]
            issue_reason = issue["reason"]
            issue_response_sha256 = issue["response"]["sha256"]
        if issue_projection is None:
            rejections["issue:" + issue_reason] += 1
            decisions.append(
                {
                    "detail_pilot_order": index - 1,
                    "candidate_id": candidate_id,
                    "projected_split": candidate["projected_split"],
                    "repository_split_group": candidate["repository_split_group"],
                    "state": "rejected",
                    "terminal_stage": "issue",
                    "reason": issue_reason,
                    "pull_source": pull_source,
                    "issue_source": issue_source,
                }
            )
            print(json.dumps({"candidate": index, "stage": "issue", "reason": issue_reason, "source": issue_source}, sort_keys=True), flush=True)
            continue

        label_key = "bug_label" if issue_projection["bug_label_matched"] else "no_bug_label"
        label_strata[label_key] += 1
        candidate_metadata.append(
            {
                "pilot_id": "ghevidence-"
                + hashlib.sha256(
                    f'{candidate_id}\0{detail["merge_commit_sha"]}'.encode("utf-8")
                ).hexdigest()[:24],
                "candidate_id": candidate_id,
                "source_dataset": "github-executable-evidence-metadata-v2",
                "projected_split": candidate["projected_split"],
                "repository_split_group": detail["repository_split_group"],
                "pr": detail,
                "linked_issue": issue_projection,
                "checkpoint_source": {"pull": pull_source, "issue": issue_source},
                "response_sha256": {
                    "pull": pull["response"]["sha256"],
                    "issue": issue_response_sha256,
                },
                "historical_license_check_deferred": True,
                "execution_qualification_pending": True,
                "content_boundaries": {
                    "patch_or_source_stored": False,
                    "raw_response_stored": False,
                    "text_or_user_identity_stored": False,
                },
                "training_admitted": False,
            }
        )
        decisions.append(
            {
                "detail_pilot_order": index - 1,
                "candidate_id": candidate_id,
                "projected_split": candidate["projected_split"],
                "repository_split_group": candidate["repository_split_group"],
                "state": "candidate",
                "terminal_stage": "issue",
                "reason": "selected",
                "bug_label_matched": issue_projection["bug_label_matched"],
                "pull_source": pull_source,
                "issue_source": issue_source,
            }
        )
        print(json.dumps({"candidate": index, "selected": len(candidate_metadata), "label_stratum": label_key, "pull_source": pull_source, "issue_source": issue_source}, sort_keys=True), flush=True)

    all_new = {
        path
        for stage in ("pull", "issue")
        for path in (new_root / stage).glob("*.json")
    }
    require(consumed_new == all_new, "v2 checkpoint tree contains unexpected entries")
    require(
        logical_requests <= config["api"]["maximum_new_logical_requests"],
        "logical request budget exceeded",
    )
    split_counts = Counter(row["projected_split"] for row in candidate_metadata)
    split_repositories = {
        split: len(
            {
                row["repository_split_group"]
                for row in candidate_metadata
                if row["projected_split"] == split
            }
        )
        for split in ("train", "validation")
    }
    gate = config["outcome_gate"]
    checks = {
        "minimum_records": len(candidate_metadata) >= gate["minimum_records"],
        **{
            f"{split}_minimum_records": split_counts[split]
            >= gate["minimum_split_records"][split]
            for split in ("train", "validation")
        },
        **{
            f"{split}_minimum_repositories": split_repositories[split]
            >= gate["minimum_split_repositories"][split]
            for split in ("train", "validation")
        },
    }
    summary = {
        "version": VERSION,
        "fixed_denominator": len(selected),
        "candidate_records": len(candidate_metadata),
        "candidate_split_counts": {
            split: split_counts[split] for split in ("train", "validation")
        },
        "candidate_split_repositories": split_repositories,
        "bug_label_strata": dict(sorted(label_strata.items())),
        "rejections": dict(sorted(rejections.items())),
        "outcome_checks": checks,
        "fixed_executable_feasibility_pilot_authorized": all(checks.values()),
        "historical_license_check_deferred": True,
        "execution_qualification_pending": True,
        "training_admitted": False,
        "gpu_used": False,
    }
    manifest_facts = {
        "network_requests": client.actual_requests,
        "new_logical_requests": logical_requests,
        "source_checkpoint_reuses": dict(sorted(source_reuses.items())),
        "v2_cached_requests": len(consumed_new) - logical_requests,
    }
    write_final_outputs(
        config,
        config_path,
        candidate_metadata,
        decisions,
        summary,
        manifest_facts,
    )
    return summary, manifest_facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)
    validate_config(config)
    selected, decisions, _denylist = load_and_validate_source(config)
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "version": VERSION,
                    "mode": "preflight-only",
                    "git_commit": current_commit(),
                    "config_sha256": sha256_file(args.config),
                    "script_sha256": sha256_file(Path(__file__)),
                    "fixed_denominator": len(selected),
                    "source_state_counts": dict(
                        sorted(Counter(row["state"] for row in decisions).items())
                    ),
                    "maximum_new_logical_requests": config["api"]["maximum_new_logical_requests"],
                    "network_requests": 0,
                    "output_writes": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    summary, manifest_facts = run(config, args.config)
    print(json.dumps({**summary, **manifest_facts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
