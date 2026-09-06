"""Score four frozen A4 candidates for one case into an atomic checkpoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from scripts.baseline.score_a3_baseline import A31_SCORING_PROTOCOL, score_prediction
from scripts.preference.a4_score_common import CHECKPOINT_VERSION, current_commit, require_clean, sha256_text, verify_inputs
from scripts.training.a3_formal_common import require, sha256_file


def write_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--case-index", type=int, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require_clean(repo)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    manifest, candidates, _ = verify_inputs(config, repo)
    cases = manifest["cases"]
    require(0 <= args.case_index < len(cases), "A4 case index out of range")
    state_path = Path(config["output"]["directory"]) / "scoring-state.json"
    require(state_path.is_file(), "A4 scoring state missing")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    commit = current_commit(repo)
    require(state["scorer_git_commit"] == commit, "A4 scorer commit changed")
    require(state["config_sha256"] == sha256_file(args.config), "A4 scoring config changed")
    item = cases[args.case_index]
    group = candidates[args.case_index * 4:(args.case_index + 1) * 4]
    require([row["candidate_index"] for row in group] == [0, 1, 2, 3], "A4 case candidates changed")
    require(all(row["case_id"] == item["case_id"] for row in group), "A4 case identity changed")
    checkpoint = Path(config["output"]["checkpoint_directory"]) / f"{args.case_index:04d}.json"
    if checkpoint.exists():
        cached = json.loads(checkpoint.read_text(encoding="utf-8"))
        require(cached["case_id"] == item["case_id"] and cached["config_sha256"] == state["config_sha256"], "A4 cached checkpoint identity changed")
        print(json.dumps({"case_index": args.case_index, "case_id": item["case_id"], "status": "cached"}, sort_keys=True))
        return
    scores = []
    bwrap = Path(config["scoring"]["bwrap"])
    case_dir = Path(config["source"]["dataset_directory"]) / "cases" / item["case_id"]
    for candidate in group:
        prediction = {"sample_id": item["case_id"], "status": candidate["status"], "raw_text": candidate["raw_text"]}
        score = score_prediction(item, case_dir, prediction, bwrap, scoring_protocol=A31_SCORING_PROTOCOL)
        score.update(
            candidate_id=candidate["candidate_id"],
            candidate_index=candidate["candidate_index"],
            source_train_sample_id=candidate["source_train_sample_id"],
            candidate_record_sha256=sha256_text(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
        )
        scores.append(score)
        print(json.dumps({"case_index": args.case_index, "candidate_id": candidate["candidate_id"], "terminal": score["terminal_classification"], "success": score["success"]}, sort_keys=True), flush=True)
    write_atomic(checkpoint, {
        "version": CHECKPOINT_VERSION,
        "mode": config["mode"],
        "config_sha256": state["config_sha256"],
        "scorer_git_commit": commit,
        "candidate_artifact_sha256": config["source"]["candidates_sha256"],
        "dataset_manifest_sha256": config["source"]["dataset_manifest_sha256"],
        "case_index": args.case_index,
        "case_id": item["case_id"],
        "task_level": item["task_level"],
        "scores": scores,
    })
    print(json.dumps({"case_index": args.case_index, "case_id": item["case_id"], "status": "written", "checkpoint": str(checkpoint)}, sort_keys=True))


if __name__ == "__main__":
    main()
