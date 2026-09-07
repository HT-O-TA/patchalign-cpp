#!/usr/bin/env python3
"""Reconstruct and prove the irreversible early stop of GitHub detail v1."""

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


VERSION = "data-v2-github-detail-early-stop-v1"
DEFAULT_CONFIG = Path("configs/data/data_v2_github_detail_early_stop_v1.json")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    require(all(isinstance(row, dict) for row in rows), f"invalid JSONL object: {path}")
    return rows


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for row in rows
    )


def verify_file(spec: Mapping[str, Any], label: str) -> Path:
    path = Path(str(spec["path"]))
    require(path.is_file(), f"missing {label}: {path}")
    require(sha256_file(path) == spec["sha256"], f"{label} hash changed")
    return path


def validate_config(config: Mapping[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected audit version")
    verify_file(config["decision"], "ADR-0020")
    source = config["source_run"]
    require(source["version"] == "data-v2-github-detail-pilot-v1", "source version changed")
    require(source["git_commit"] == "bb30de8fb2327e53bd384d59baada235c56fd168", "source commit changed")
    require(source["slurm_job_id"] == 96959, "source Job changed")
    require(source["terminal_state"] == "CANCELLED by 1039", "terminal state changed")
    require(source["elapsed"] == "04:10:31", "source elapsed changed")
    require(source["started_at"] == "2026-09-07T13:21:16Z", "source start changed")
    require(source["ended_at"] == "2026-09-07T17:31:47Z", "source end changed")
    require(source["node"] == "gpu25", "source node changed")
    verify_file(source["config"], "source config")
    verify_file(source["script"], "source script")
    selected = source["selected_candidates"]
    verify_file(selected, "selected candidates")
    require(selected["count"] == 200, "fixed denominator changed")
    require(selected["split_counts"] == {"train": 160, "validation": 40}, "split counts changed")
    require(selected["split_order"] == ["train", "validation"], "split order changed")
    require(source["checkpoint_counts"] == {"pull": 145, "issue": 81, "license": 20}, "checkpoint counts changed")
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
        config["scope"]
        == {
            "network_requests": 0,
            "patch_or_source_read": False,
            "raw_response_read": False,
            "training_admitted": False,
            "gpu_authorized": False,
            "dpo_authorized": False,
        },
        "scope changed",
    )
    require(
        config["output_directory"]
        == "artifacts/data-v2/github-detail-pilot-v1/early-stop-audit-v1",
        "output path changed",
    )


def validate_checkpoint(
    checkpoint: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> None:
    for key, value in expected.items():
        require(checkpoint.get(key) == value, f"{label} binding changed: {key}")
    require(isinstance(checkpoint.get("accepted"), bool), f"{label} accepted invalid")
    require(isinstance(checkpoint.get("reason"), str), f"{label} reason invalid")
    projection = checkpoint.get("projection")
    require(
        (checkpoint["accepted"] and isinstance(projection, dict))
        or (not checkpoint["accepted"] and projection is None),
        f"{label} projection/accepted mismatch",
    )
    response = checkpoint.get("response")
    require(isinstance(response, dict), f"{label} response metadata missing")
    require(SHA256_RE.fullmatch(str(response.get("sha256"))) is not None, f"{label} response hash invalid")
    require(isinstance(response.get("http_status"), int), f"{label} HTTP status invalid")
    require(isinstance(checkpoint.get("request_url"), str), f"{label} request URL missing")


def checkpoint_inventory(root: Path, expected_counts: Mapping[str, int]) -> tuple[list[dict[str, str]], str]:
    inventory: list[dict[str, str]] = []
    for stage in ("pull", "issue", "license"):
        directory = root / stage
        require(directory.is_dir(), f"missing checkpoint directory: {directory}")
        temporary = list(directory.glob("*.tmp"))
        require(not temporary, f"temporary checkpoint remains in {stage}")
        paths = sorted(directory.glob("*.json"))
        require(len(paths) == expected_counts[stage], f"{stage} checkpoint count changed")
        for path in paths:
            inventory.append(
                {"path": f"{stage}/{path.name}", "sha256": sha256_file(path)}
            )
    return inventory, sha256_bytes(canonical(inventory))


def _common(config: Mapping[str, Any]) -> dict[str, Any]:
    source = config["source_run"]
    return {
        "version": source["version"],
        "config_sha256": source["config"]["sha256"],
        "script_sha256": source["script"]["sha256"],
        "git_commit": source["git_commit"],
        "selection_sha256": source["selected_candidates"]["sha256"],
    }


def reconstruct(
    config: Mapping[str, Any],
    selected: list[dict[str, Any]],
    checkpoint_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source = config["source_run"]
    require(len(selected) == source["selected_candidates"]["count"], "selected count changed")
    ids = [str(row.get("candidate_id") or "") for row in selected]
    require(all(re.fullmatch(r"ghpr-[0-9a-f]{24}", value) for value in ids), "invalid candidate ID")
    require(len(set(ids)) == len(ids), "duplicate candidate ID")
    expected_splits = ["train"] * 160 + ["validation"] * 40
    require([row.get("projected_split") for row in selected] == expected_splits, "fixed split order changed")
    require(
        [row.get("detail_pilot_order") for row in selected] == list(range(len(selected))),
        "pilot order changed",
    )
    common = _common(config)
    decisions: list[dict[str, Any]] = []
    qualified: list[dict[str, Any]] = []
    consumed_checkpoints: set[Path] = set()
    terminal_seen_gap = False

    for index, candidate in enumerate(selected, start=1):
        candidate_id = candidate["candidate_id"]
        split = candidate["projected_split"]
        repository = candidate["repository_split_group"]
        state = "unstarted"
        stage = "pull"
        reason = "checkpoint_missing"
        pull_path = checkpoint_root / "pull" / f"{candidate_id}.json"
        if pull_path.is_file():
            consumed_checkpoints.add(pull_path)
            require(not terminal_seen_gap, "pull checkpoints are not a contiguous prefix")
            pull = load_json(pull_path)
            validate_checkpoint(
                pull, {**common, "candidate_id": candidate_id, "stage": "pull"}, f"pull/{candidate_id}"
            )
            if not pull["accepted"]:
                state, reason = "rejected", pull["reason"]
            else:
                detail = pull["projection"]
                require(detail["repository_split_group"] == repository, "pull repository changed")
                issue_path = checkpoint_root / "issue" / f"{candidate_id}.json"
                if not issue_path.is_file():
                    state, stage, reason = "incomplete", "issue", "checkpoint_missing"
                else:
                    consumed_checkpoints.add(issue_path)
                    issue = load_json(issue_path)
                    validate_checkpoint(
                        issue,
                        {**common, "candidate_id": candidate_id, "stage": "issue"},
                        f"issue/{candidate_id}",
                    )
                    if not issue["accepted"]:
                        state, stage, reason = "rejected", "issue", issue["reason"]
                    else:
                        repository_id = hashlib.sha256(repository.encode("utf-8")).hexdigest()[:24]
                        license_path = checkpoint_root / "license" / f"ghrepo-{repository_id}.json"
                        if not license_path.is_file():
                            state, stage, reason = "incomplete", "license", "checkpoint_missing"
                        else:
                            consumed_checkpoints.add(license_path)
                            license_result = load_json(license_path)
                            validate_checkpoint(
                                license_result,
                                {**common, "repository_split_group": repository, "stage": "license"},
                                f"license/{repository_id}",
                            )
                            if not license_result["accepted"]:
                                state, stage, reason = (
                                    "rejected",
                                    "license",
                                    license_result["reason"],
                                )
                            else:
                                state, stage, reason = "qualified", "license", "selected"
                                qualified.append(
                                    {
                                        "pilot_id": "ghdetail-"
                                        + hashlib.sha256(
                                            f'{candidate_id}\0{detail["merge_commit_sha"]}'.encode("utf-8")
                                        ).hexdigest()[:24],
                                        "candidate_id": candidate_id,
                                        "source_dataset": "github-issue-linked-cpp-detail-v1",
                                        "projected_split": split,
                                        "repository_split_group": repository,
                                        "pr": detail,
                                        "linked_issue": issue["projection"],
                                        "license": license_result["projection"],
                                        "response_sha256": {
                                            "pull": pull["response"]["sha256"],
                                            "issue": issue["response"]["sha256"],
                                            "license": license_result["response"]["sha256"],
                                        },
                                        "content_boundaries": {
                                            "patch_or_source_stored": False,
                                            "raw_response_stored": False,
                                            "text_or_user_identity_stored": False,
                                        },
                                        "training_admitted": False,
                                    }
                                )
        else:
            terminal_seen_gap = True
        if state == "incomplete":
            terminal_seen_gap = True
        decisions.append(
            {
                "detail_pilot_order": index - 1,
                "candidate_id": candidate_id,
                "projected_split": split,
                "repository_split_group": repository,
                "state": state,
                "terminal_stage": stage,
                "reason": reason,
            }
        )

    all_checkpoints = {
        path
        for checkpoint_stage in ("pull", "issue", "license")
        for path in (checkpoint_root / checkpoint_stage).glob("*.json")
    }
    require(
        consumed_checkpoints == all_checkpoints,
        "checkpoint tree contains unexpected or unreachable entries",
    )
    terminal_states = {"qualified", "rejected"}
    completed_prefix = 0
    for decision in decisions:
        if decision["state"] not in terminal_states:
            break
        completed_prefix += 1
    require(
        all(item["state"] not in terminal_states for item in decisions[completed_prefix:]),
        "terminal candidate appears after incomplete/unstarted boundary",
    )
    observed_counts = Counter(row["projected_split"] for row in qualified)
    observed_repositories = {
        split: {
            row["repository_split_group"]
            for row in qualified
            if row["projected_split"] == split
        }
        for split in ("train", "validation")
    }
    remaining = {
        split: [
            row
            for row in decisions
            if row["projected_split"] == split and row["state"] not in terminal_states
        ]
        for split in ("train", "validation")
    }
    optimistic_counts = {
        split: observed_counts[split] + len(remaining[split])
        for split in ("train", "validation")
    }
    optimistic_repositories = {
        split: len(
            observed_repositories[split]
            | {row["repository_split_group"] for row in remaining[split]}
        )
        for split in ("train", "validation")
    }
    gate = config["outcome_gate"]
    reachability = {
        "minimum_records": sum(optimistic_counts.values()) >= gate["minimum_records"],
        **{
            f"{split}_minimum_records": optimistic_counts[split]
            >= gate["minimum_split_records"][split]
            for split in ("train", "validation")
        },
        **{
            f"{split}_minimum_repositories": optimistic_repositories[split]
            >= gate["minimum_split_repositories"][split]
            for split in ("train", "validation")
        },
    }
    rejection_counts = Counter(
        f'{row["terminal_stage"]}:{row["reason"]}'
        for row in decisions
        if row["state"] == "rejected"
    )
    summary = {
        "version": VERSION,
        "source_job": source["slurm_job_id"],
        "fixed_denominator": len(selected),
        "completed_prefix": completed_prefix,
        "candidate_states": dict(Counter(row["state"] for row in decisions)),
        "qualified_records": len(qualified),
        "qualified_split_counts": {
            split: observed_counts[split] for split in ("train", "validation")
        },
        "qualified_split_repositories": {
            split: len(observed_repositories[split]) for split in ("train", "validation")
        },
        "rejections": dict(sorted(rejection_counts.items())),
        "remaining_split_counts": {
            split: len(remaining[split]) for split in ("train", "validation")
        },
        "optimistic_upper_bound_split_records": optimistic_counts,
        "optimistic_upper_bound_split_repositories": optimistic_repositories,
        "outcome_gate_reachability": reachability,
        "outcome_gate_irrecoverable": not all(reachability.values()),
        "execution_content_pilot_authorized": False,
        "network_requests": 0,
        "patch_or_source_read": False,
        "training_admitted": False,
        "gpu_used": False,
    }
    return decisions, qualified, summary


def write_outputs(
    config: Mapping[str, Any],
    config_path: Path,
    decisions: list[dict[str, Any]],
    qualified: list[dict[str, Any]],
    summary: dict[str, Any],
    inventory: list[dict[str, str]],
    inventory_sha256: str,
) -> None:
    output = Path(config["output_directory"])
    require(not output.exists(), f"refusing to overwrite output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + "-building-", dir=output.parent))
    try:
        files = {
            "decisions.jsonl": jsonl_bytes(decisions),
            "qualified-prefix.jsonl": jsonl_bytes(qualified),
            "checkpoint-inventory.json": json.dumps(
                inventory, ensure_ascii=False, indent=2, sort_keys=True
            ).encode("utf-8")
            + b"\n",
            "summary.json": json.dumps(
                summary, ensure_ascii=False, indent=2, sort_keys=True
            ).encode("utf-8")
            + b"\n",
        }
        for name, payload in files.items():
            (temporary / name).write_bytes(payload)
        manifest = {
            "version": VERSION,
            "git_commit": os.environ.get("PATCHALIGN_GIT_COMMIT", ""),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_sha256": sha256_file(config_path),
            "script_sha256": sha256_file(Path(__file__)),
            "source_job": config["source_run"],
            "checkpoint_inventory_sha256": inventory_sha256,
            "outputs": {
                name: {"sha256": sha256_bytes(payload)} for name, payload in files.items()
            },
            "content_boundaries": config["scope"],
        }
        (temporary / "run-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)
    validate_config(config)
    source = config["source_run"]
    selected = read_jsonl(Path(source["selected_candidates"]["path"]))
    root = Path(source["checkpoint_root"])
    inventory, inventory_sha = checkpoint_inventory(root, source["checkpoint_counts"])
    decisions, qualified, summary = reconstruct(config, selected, root)
    require(summary["outcome_gate_irrecoverable"] is True, "early stop is not proven")
    if args.preflight_only:
        print(json.dumps({**summary, "mode": "preflight-only", "checkpoint_inventory_sha256": inventory_sha}, indent=2, sort_keys=True))
        return
    write_outputs(
        config,
        args.config,
        decisions,
        qualified,
        summary,
        inventory,
        inventory_sha,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
