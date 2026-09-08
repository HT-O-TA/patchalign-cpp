#!/usr/bin/env python3
"""Freeze the balanced, repository-unique 20-case GitHub execution denominator."""

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
from typing import Any, Mapping


VERSION = "data-v2-github-execution-feasibility-selection-v1"
DEFAULT_CONFIG = Path(
    "configs/data/data_v2_github_execution_feasibility_selection_v1.json"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_hash(*values: object) -> str:
    return sha256_bytes("\0".join(str(value) for value in values).encode("utf-8"))


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
    require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "invalid Git commit")
    return value


def validate_config(config: Mapping[str, Any]) -> None:
    require(config.get("version") == VERSION, "unexpected selection version")
    verify_file(config["decision"], "ADR-0021")
    source = config["source_metadata"]
    require(
        source["version"] == "data-v2-github-executable-evidence-metadata-v2",
        "source version changed",
    )
    require(
        source["git_commit"] == "76161d56ec6a502f968cd1bf69a85d9f4e9ee6a0",
        "source commit changed",
    )
    require(source["slurm_job_id"] == 97210, "source Job changed")
    require(source["candidates"]["count"] == 104, "source count changed")
    for key in ("candidates", "summary", "run_manifest"):
        verify_file(source[key], f"source {key}")
    summary = load_json(Path(source["summary"]["path"]))
    require(
        summary["fixed_executable_feasibility_pilot_authorized"] is True,
        "metadata outcome gate did not pass",
    )
    require(
        summary["candidate_split_counts"] == {"train": 86, "validation": 18},
        "source split counts changed",
    )
    require(
        summary["candidate_split_repositories"] == {"train": 81, "validation": 14},
        "source repository counts changed",
    )
    manifest = load_json(Path(source["run_manifest"]["path"]))
    require(manifest["git_commit"] == source["git_commit"], "manifest commit changed")
    require(str(manifest["slurm_job_id"]) == str(source["slurm_job_id"]), "manifest Job changed")
    require(manifest["config_sha256"] == source["config_sha256"], "manifest config changed")
    require(manifest["script_sha256"] == source["script_sha256"], "manifest script changed")
    require(
        manifest["outputs"]["candidate-metadata.jsonl"]["sha256"]
        == source["candidates"]["sha256"],
        "candidate reverse binding changed",
    )
    require(
        manifest["outputs"]["summary.json"]["sha256"]
        == source["summary"]["sha256"],
        "summary reverse binding changed",
    )
    selection = config["selection"]
    require(selection["seed"] == 20260908, "selection seed changed")
    require(
        selection["split_stratum_targets"]
        == {
            "train": {"bug_label": 8, "no_bug_label": 8},
            "validation": {"bug_label": 2, "no_bug_label": 2},
        },
        "selection quotas changed",
    )
    require(selection["split_order"] == ["train", "validation"], "split order changed")
    require(selection["stratum_order"] == ["bug_label", "no_bug_label"], "stratum order changed")
    require(selection["repository_unique_across_fixed_denominator"] is True, "repository uniqueness disabled")
    require(selection["replacement_after_selection"] is False, "replacement enabled")
    require(
        selection["rank"]
        == "sha256(seed_nul_split_nul_stratum_nul_repository_nul_candidate_id)",
        "ranking changed",
    )
    require(
        config["scope"]
        == {
            "metadata_read_only": True,
            "network_requests": 0,
            "patch_or_source_read": False,
            "license_read": False,
            "execution_performed": False,
            "training_admitted": False,
            "gpu_authorized": False,
            "dpo_authorized": False,
        },
        "scope changed",
    )
    require(
        config["output_directory"]
        == "artifacts/data-v2/github-executable-evidence-v2/feasibility-selection-v1",
        "output path changed",
    )


def label_stratum(row: Mapping[str, Any]) -> str:
    return "bug_label" if row["linked_issue"]["bug_label_matched"] else "no_bug_label"


def select_fixed(
    rows: list[dict[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    require(len(rows) == config["source_metadata"]["candidates"]["count"], "source count changed")
    ids = [str(row.get("candidate_id") or "") for row in rows]
    require(len(set(ids)) == len(ids), "duplicate candidate ID")
    require(
        all(re.fullmatch(r"ghpr-[0-9a-f]{24}", value) for value in ids),
        "invalid candidate ID",
    )
    seed = config["selection"]["seed"]
    targets = config["selection"]["split_stratum_targets"]
    selected: list[dict[str, Any]] = []
    used_repositories: set[str] = set()
    for split in config["selection"]["split_order"]:
        queues: dict[str, list[dict[str, Any]]] = {}
        for stratum in config["selection"]["stratum_order"]:
            matching = [
                row
                for row in rows
                if row["projected_split"] == split and label_stratum(row) == stratum
            ]
            queues[stratum] = sorted(
                matching,
                key=lambda row: (
                    stable_hash(
                        seed,
                        split,
                        stratum,
                        row["repository_split_group"],
                        row["candidate_id"],
                    ),
                    row["candidate_id"],
                ),
            )
        counts = Counter()
        while any(counts[key] < targets[split][key] for key in queues):
            progressed = False
            for stratum in config["selection"]["stratum_order"]:
                if counts[stratum] >= targets[split][stratum]:
                    continue
                while queues[stratum]:
                    row = queues[stratum].pop(0)
                    repository = row["repository_split_group"]
                    if repository in used_repositories:
                        continue
                    copied = dict(row)
                    copied["feasibility_order"] = len(selected)
                    copied["selection_stratum"] = stratum
                    copied["replacement_allowed"] = False
                    selected.append(copied)
                    used_repositories.add(repository)
                    counts[stratum] += 1
                    progressed = True
                    break
            require(progressed, f"insufficient unique repositories for {split} quotas")
    require(len(selected) == 20, "fixed feasibility denominator changed")
    require(len(used_repositories) == 20, "selected repositories are not unique")
    return selected


def write_outputs(
    config: Mapping[str, Any], config_path: Path, selected: list[dict[str, Any]]
) -> None:
    output = Path(config["output_directory"])
    require(not output.exists(), f"refusing to overwrite selection: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + "-building-", dir=output.parent))
    try:
        selected_payload = jsonl_bytes(selected)
        counts = Counter(
            (row["projected_split"], row["selection_stratum"]) for row in selected
        )
        summary = {
            "version": VERSION,
            "fixed_denominator": len(selected),
            "unique_repositories": len(
                {row["repository_split_group"] for row in selected}
            ),
            "split_stratum_counts": {
                split: {
                    stratum: counts[(split, stratum)]
                    for stratum in config["selection"]["stratum_order"]
                }
                for split in config["selection"]["split_order"]
            },
            "replacement_allowed": False,
            "content_acquired": False,
            "execution_performed": False,
            "training_admitted": False,
            "gpu_used": False,
        }
        summary_payload = (
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            )
            + b"\n"
        )
        (temporary / "selected-candidates.jsonl").write_bytes(selected_payload)
        (temporary / "summary.json").write_bytes(summary_payload)
        manifest = {
            "version": VERSION,
            "git_commit": current_commit(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_sha256": sha256_file(config_path),
            "script_sha256": sha256_file(Path(__file__)),
            "source_metadata_manifest_sha256": config["source_metadata"]["run_manifest"]["sha256"],
            "content_boundaries": config["scope"],
            "outputs": {
                "selected-candidates.jsonl": {
                    "count": len(selected),
                    "sha256": sha256_bytes(selected_payload),
                },
                "summary.json": {"sha256": sha256_bytes(summary_payload)},
            },
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
    args = parser.parse_args()
    config = load_json(args.config)
    validate_config(config)
    rows = read_jsonl(Path(config["source_metadata"]["candidates"]["path"]))
    selected = select_fixed(rows, config)
    write_outputs(config, args.config, selected)
    print(
        json.dumps(
            {
                "version": VERSION,
                "fixed_denominator": len(selected),
                "unique_repositories": len(
                    {row["repository_split_group"] for row in selected}
                ),
                "output_directory": config["output_directory"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
