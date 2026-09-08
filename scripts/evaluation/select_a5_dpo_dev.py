#!/usr/bin/env python3
"""Select one A5 DPO variant from frozen independent dev execution summaries."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.evaluation.a5_dpo_dev_common import ROLES, read_json, select_variant, validate_config
from scripts.training.a3_formal_common import require, sha256_file, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 dev selection requires a clean worktree")
    output = Path(config["outputs"]["selection"])
    require(not output.exists(), "refusing to overwrite A5 dev selection")
    summaries = {
        role: read_json(Path(config["outputs"]["scoring_root"]) / role / "summary.json")
        for role in ROLES
    }
    metrics = {role: summary["selection_metrics"] for role, summary in summaries.items()}
    decision = select_variant(metrics)
    decision.update({
        "version": "a5-dpo-dev-selection-v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "config_sha256": sha256_file(args.config),
        "summary_sha256": {
            role: sha256_file(Path(config["outputs"]["scoring_root"]) / role / "summary.json")
            for role in ROLES
        },
        "formal_evaluation_required": True,
        "result_label": "positive_candidate" if decision["selected_is_promotable"] else "negative_or_no_improvement_candidate",
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, decision)
    print(json.dumps(decision, sort_keys=True))


if __name__ == "__main__":
    main()
