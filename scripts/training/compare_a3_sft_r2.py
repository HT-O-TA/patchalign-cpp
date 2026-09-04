"""Run the frozen A3.4 promotion comparison and a separate M1 diagnostic."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from patchalign.evaluation.gates import (
    MetricSnapshot,
    evaluate_training_gate,
    load_quality_gate_config,
    paired_bootstrap_difference,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json
from scripts.training.compare_a3_formal import snapshot


VERSION = "a3-sft-r2-comparison-v1"
EXPECTED_ROLES = {
    "m0": "promotion_baseline",
    "m1": "diagnostic_baseline",
    "m1_r2": "candidate",
}
EXPECTED_HASHES = {
    "m0": {
        "predictions.jsonl": "sha256:dadf0cfe5c0178ed3b2497536c8509a8437f9f8461f7c10ec86591cd99d7429e",
        "run-manifest.json": "sha256:8c35904e2ab2f5118c9b8fbec7913c51a45394779dc03a38e5421d3e2e28a87d",
        "generation-summary.json": "sha256:0819e4867de715aa18ce2bc019ad675db5e4981100b49a19aade6fa213b605bf",
        "scores.jsonl": "sha256:92ceb428df80ed772a2c9ce4dfaefd0f3d9b36fd7d96cc74e5cafd538fd6df3d",
        "score-summary.json": "sha256:f183fa2cf203c2be95dbab1a56bfe13ec9718c117da14f0ed0592c45376a5ed0",
        "score-manifest.json": "sha256:6e1b6f097c30f602a43b93cacff2cda83d589cfabccc5528755c0efab549ae6d",
    },
    "m1": {
        "predictions.jsonl": "sha256:e688dd57909866ca8f39c4675554842fca08fab1805374995aa169b33b3077cc",
        "run-manifest.json": "sha256:7cba5733def997880d05c6289ce53add91adec9b4ed0442736cabbac8437ad14",
        "generation-summary.json": "sha256:e25683b6623324142a3f8100627434e915c9e20d7ce198fafcf315b01288e133",
        "scores.jsonl": "sha256:2191dd1d5f93839dccb36fd8e10e23242bb56eb9853b793c895c64435359d7f8",
        "score-summary.json": "sha256:880aa2735238fd8136e894db3a5dc58aa2aa566d293aba4b1e0ab7bf52250cf9",
        "score-manifest.json": "sha256:57e3032fd18d40de394dc09a6c0a39ceabc4431221071006b011e3dc7996cf27",
    },
    "m1_r2": {
        "predictions.jsonl": "sha256:c5fe4e6d90d59c24f749949c8df4f074e2b26f6af625e960ce95013367e7bb6a",
        "run-manifest.json": "sha256:88abe6053202e8b81e0332166c3e6b66fefca3e50a0f36b39cdffae086983878",
        "generation-summary.json": "sha256:eb82f96cef4c103a4944f888f0d171307f1a25d3b35b15d780d5c18b1d26c09a",
        "scores.jsonl": "sha256:f05b54a107850591c0cfc16564ef477488cacfe50cb6b703ace41fb093c650b8",
        "score-summary.json": "sha256:23ee63ff54375d200842acb392ccb6c1664e263e7ae0790820c386f53c2b1c07",
        "score-manifest.json": "sha256:b6d72c856bccb512ed228978a6778464e91a2138ccfaebdfdfa08c10bc714bf2",
    },
}
QUALITY_GATE_SHA256 = "sha256:6ba153f1ec3d56a41eab0048595a5169816df5e404a37c44c3097b7f375f5af1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong comparison config version")
    require(config.get("formal_denominators") == {"all": 500, "function": 400, "file_window": 100}, "wrong formal denominators")
    quality = config["quality_gates"]
    require(quality["path"] == "configs/evaluation/quality_gates_v1.json", "wrong quality gate path")
    require(quality["sha256"] == QUALITY_GATE_SHA256, "quality gate identity changed")
    require(set(config["models"]) == set(EXPECTED_ROLES), "wrong comparison model set")
    for name, role in EXPECTED_ROLES.items():
        model = config["models"][name]
        require(model["role"] == role, f"wrong role for {name}")
        require(model["hashes"] == EXPECTED_HASHES[name], f"artifact identities changed for {name}")
    require(
        config["output_directory"]
        == "/mingli01/project/ht/patchalign-cpp/artifacts/a3/sft-r2/comparison-v1",
        "wrong comparison output directory",
    )


def artifact_path(model: dict[str, Any], filename: str) -> Path:
    if filename in {"predictions.jsonl", "run-manifest.json", "generation-summary.json"}:
        return Path(model["inference_directory"]) / filename
    return Path(model["score_directory"]) / filename


def verify_artifacts(config: dict[str, Any]) -> None:
    for name, model in config["models"].items():
        for filename, expected in model["hashes"].items():
            path = artifact_path(model, filename)
            require(path.is_file(), f"missing {name} artifact: {filename}")
            require(sha256_file(path) == expected, f"{name} artifact hash mismatch: {filename}")


def row_timed_out(row: dict[str, Any]) -> bool:
    for stage in row.get("stages", {}).values():
        if not isinstance(stage, dict):
            continue
        if stage.get("timed_out") is True:
            return True
        if any(outcome.get("timed_out") is True for outcome in stage.get("outcomes", [])):
            return True
    return False


def _transition_ids(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    predicate,
) -> dict[str, list[str]]:
    before = {row["case_id"] for row in baseline_rows if predicate(row)}
    after = {row["case_id"] for row in candidate_rows if predicate(row)}
    return {"introduced": sorted(after - before), "resolved": sorted(before - after), "retained": sorted(before & after)}


def diagnostic_comparison(
    baseline: MetricSnapshot,
    candidate: MetricSnapshot,
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    gate_config: dict[str, Any],
) -> dict[str, Any]:
    require(
        [row["case_id"] for row in baseline_rows] == [row["case_id"] for row in candidate_rows],
        "M1/M1-R2 score order mismatch",
    )
    bootstrap = gate_config["paired_bootstrap"]
    function_ci = paired_bootstrap_difference(
        baseline.function_pass_at_1,
        candidate.function_pass_at_1,
        confidence_level=bootstrap["confidence_level"],
        resamples=bootstrap["resamples"],
        seed=bootstrap["seed"],
    )
    file_window_ci = paired_bootstrap_difference(
        baseline.file_window_pass_at_1,
        candidate.file_window_pass_at_1,
        confidence_level=bootstrap["confidence_level"],
        resamples=bootstrap["resamples"],
        seed=bootstrap["seed"],
    )
    return {
        "version": "a3-sft-r2-diagnostic-v1",
        "baseline": "M1",
        "candidate": "M1-R2",
        "promotion_gate": False,
        "denominators": {
            "all": len(baseline_rows),
            "function": len(baseline.function_pass_at_1),
            "file_window": len(baseline.file_window_pass_at_1),
        },
        "counts": {
            "function_pass": [sum(baseline.function_pass_at_1), sum(candidate.function_pass_at_1)],
            "file_window_pass": [sum(baseline.file_window_pass_at_1), sum(candidate.file_window_pass_at_1)],
            "total_pass": [sum(row["success"] for row in baseline_rows), sum(row["success"] for row in candidate_rows)],
        },
        "rate_deltas": {
            "parse_rate": candidate.parse_rate - baseline.parse_rate,
            "apply_rate": candidate.apply_rate - baseline.apply_rate,
            "compile_rate": candidate.compile_rate - baseline.compile_rate,
            "regression_rate": candidate.regression_rate - baseline.regression_rate,
            "timeout_rate": candidate.timeout_rate - baseline.timeout_rate,
        },
        "paired_bootstrap": {"function": function_ci, "file_window": file_window_ci},
        "transitions": {
            "success": _transition_ids(baseline_rows, candidate_rows, lambda row: row["success"]),
            "timeout": _transition_ids(baseline_rows, candidate_rows, row_timed_out),
            "regression_failure": _transition_ids(
                baseline_rows,
                candidate_rows,
                lambda row: row["terminal_classification"] == "regression_failed",
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    config = load_json(args.config)
    validate_config(config)
    require(sha256_file(repo / config["quality_gates"]["path"]) == QUALITY_GATE_SHA256, "quality gate file hash mismatch")
    verify_artifacts(config)
    output_dir = Path(config["output_directory"])
    require(not output_dir.exists(), f"refusing to overwrite comparison directory: {output_dir}")

    loaded: dict[str, tuple[MetricSnapshot, dict[str, Any], list[dict[str, Any]]]] = {}
    rows: dict[str, list[dict[str, Any]]] = {}
    for name, model in config["models"].items():
        loaded[name] = snapshot(Path(model["score_directory"]), Path(model["inference_directory"]))
        rows[name] = load_jsonl(Path(model["score_directory"]) / "scores.jsonl")
    prompt_identities = []
    for name in ("m0", "m1", "m1_r2"):
        prompt_identities.append([
            (item["sample_id"], item["prompt_version"], item["prompt_sha256"])
            for item in loaded[name][2]
        ])
    require(prompt_identities[0] == prompt_identities[1] == prompt_identities[2], "M0/M1/M1-R2 prompt identity mismatch")

    gates = load_quality_gate_config(repo / config["quality_gates"]["path"])
    promotion_gate = evaluate_training_gate("sft", loaded["m0"][0], loaded["m1_r2"][0], gates)
    internal_reasons = [reason for reason in promotion_gate["reasons"] if reason != "external_denominator_mismatch"]
    promotion = {
        "version": "a3-sft-r2-promotion-comparison-v1",
        "baseline": "M0",
        "candidate": "M1-R2",
        "internal_gate_passed": not internal_reasons,
        "internal_gate_reasons": internal_reasons,
        "full_promotion_gate_passed": promotion_gate["passed"],
        "external_gate_status": "not_evaluated",
        "external_gate_requirement": "Defects4C >=150 paired cases",
        "gate": promotion_gate,
        "baseline_summary": loaded["m0"][1],
        "candidate_summary": loaded["m1_r2"][1],
    }
    diagnostic = diagnostic_comparison(loaded["m1"][0], loaded["m1_r2"][0], rows["m1"], rows["m1_r2"], gates)

    output_dir.mkdir(parents=True)
    promotion_path = output_dir / "promotion-vs-m0.json"
    diagnostic_path = output_dir / "diagnostic-vs-m1.json"
    manifest_path = output_dir / "comparison-manifest.json"
    write_json(promotion_path, promotion)
    write_json(diagnostic_path, diagnostic)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    manifest = {
        "version": VERSION,
        "created_at": utc_now(),
        "git_commit": commit,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "config_sha256": sha256_file(args.config),
        "quality_gate_sha256": QUALITY_GATE_SHA256,
        "input_hashes": {name: model["hashes"] for name, model in config["models"].items()},
        "outputs": {
            promotion_path.name: sha256_file(promotion_path),
            diagnostic_path.name: sha256_file(diagnostic_path),
        },
        "internal_gate_passed": promotion["internal_gate_passed"],
        "full_promotion_gate_passed": promotion["full_promotion_gate_passed"],
    }
    write_json(manifest_path, manifest)
    print(json.dumps({
        "internal_gate_passed": promotion["internal_gate_passed"],
        "full_promotion_gate_passed": promotion["full_promotion_gate_passed"],
        "reasons": promotion_gate["reasons"],
        "output_directory": str(output_dir),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
