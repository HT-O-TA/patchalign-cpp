"""Validate frozen A4 scoring inputs and create a resumable scoring state."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from scripts.preference.a4_score_common import STATE_VERSION, current_commit, require_clean, verify_inputs
from scripts.preference.build_a4_executable_candidates import MODE
from scripts.training.a3_formal_common import require, sha256_file, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require_clean(repo)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    manifest, candidates, prompts = verify_inputs(config, repo)
    output = Path(config["output"]["directory"])
    state_path = output / "scoring-state.json"
    expected = {
        "version": STATE_VERSION,
        "mode": MODE,
        "scorer_git_commit": current_commit(repo),
        "config_sha256": sha256_file(args.config),
        "candidate_artifact_sha256": config["source"]["candidates_sha256"],
        "dataset_manifest_sha256": config["source"]["dataset_manifest_sha256"],
        "case_count": len(manifest["cases"]),
        "candidate_count": len(candidates),
        "prompt_count": len(prompts),
    }
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            require(state.get(key) == value, f"A4 scoring resume mismatch: {key}")
    else:
        require(not output.exists(), "A4 scoring output exists without state")
        (output / "checkpoints").mkdir(parents=True)
        write_json(state_path, {**expected, "created_at": utc_now(), "slurm_job_id": os.environ.get("SLURM_JOB_ID")})
    print(json.dumps({"state": str(state_path), "cases": len(manifest["cases"]), "candidates": len(candidates), "config_sha256": expected["config_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
