#!/usr/bin/env python3
"""Execute-score the selected A5 DPO prediction for one Defects4C case."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.evaluation.a5_dpo_final_common import (
    inference_dir,
    read_json,
    read_jsonl,
    scoring_dir,
    validate_config,
    verify_dataset,
    verify_selection_and_adapter,
)
from scripts.external.score_defects4c_case import score_role
from scripts.training.a3_formal_common import require, sha256_file, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index", type=int, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = read_json(args.config)
    validate_config(repo, config)
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "A5 Defects4C scorer requires a clean worktree")
    verify_selection_and_adapter(config)
    _, manifest = verify_dataset(config, "defects4c")
    require(0 <= args.index < len(manifest["cases"]), "Defects4C score index outside denominator")
    candidate_dir = inference_dir(config, "defects4c")
    run_manifest = read_json(candidate_dir / "run-manifest.json")
    predictions_path = candidate_dir / "predictions.jsonl"
    require(run_manifest["config_sha256"] == sha256_file(args.config), "Defects4C inference config mismatch")
    require(run_manifest["prediction_artifact_sha256"] == sha256_file(predictions_path), "Defects4C predictions changed")
    require(run_manifest["adapter_sha256"] == config["adapter"]["sha256"], "Defects4C inference adapter mismatch")
    predictions = read_jsonl(predictions_path)
    require(len(predictions) == len(manifest["cases"]), "Defects4C prediction denominator changed")
    case = manifest["cases"][args.index]
    prediction = predictions[args.index]
    require(prediction["sample_id"] == case["case_id"], "Defects4C prediction order changed")
    identity = {
        "version": "a5-dpo-defects4c-score-case-v1",
        "index": args.index,
        "case": case,
        "config_sha256": sha256_file(args.config),
        "dataset_manifest_sha256": config["datasets"]["defects4c"]["manifest_sha256"],
        "prediction_sha256": run_manifest["prediction_artifact_sha256"],
        "adapter_sha256": config["adapter"]["sha256"],
    }
    checkpoint = scoring_dir(config, "defects4c") / "cases" / f"{args.index:03d}.json"
    if checkpoint.exists():
        cached = read_json(checkpoint)
        require(cached["identity"] == identity, "Defects4C score checkpoint identity changed")
        print(json.dumps(cached, ensure_ascii=False, sort_keys=True))
        return
    dataset = config["datasets"]["defects4c"]
    scoring_config = {
        "qualification": dataset["qualification"],
        "runtime": dataset["runtime"],
        "scoring": dataset["scoring"],
    }
    result = score_role(scoring_config, case, "dpo_beta03", prediction, repo)
    payload = {"identity": identity, "finished_at": utc_now(), "result": result}
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    temporary = checkpoint.with_suffix(".json.tmp")
    write_json(temporary, payload)
    temporary.replace(checkpoint)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
