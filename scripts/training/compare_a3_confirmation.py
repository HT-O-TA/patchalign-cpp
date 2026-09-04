"""Compare M0 and M1-R2 on the frozen unseen A3 confirmation set."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from patchalign.evaluation.gates import paired_bootstrap_difference
from scripts.training.a3_formal_common import require, sha256_file, write_json

VERSION = "a3-confirmation-comparison-v1"
MANIFEST_SHA = "sha256:7adf960fff4e7f1ee3ca95539ffa1196c3421805659c94bb46a29d0022690917"
PROMPT_SHA = "sha256:cf141a9d4f90c8fd9f1a8f9cd03509cc2b2fd48905a3c1e533e93cad702ad58f"
ADAPTER_SHA = "sha256:8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong confirmation comparison version")
    require(config["dataset"] == {
        "manifest_sha256": MANIFEST_SHA,
        "prompt_artifact_sha256": PROMPT_SHA,
        "denominators": {"all": 124, "function": 100, "file_window": 24},
    }, "confirmation dataset identity changed")
    require(config["models"]["m0"]["adapter_sha256"] is None, "M0 adapter must be null")
    require(config["models"]["m1_r2"]["adapter_sha256"] == ADAPTER_SHA, "R2 adapter changed")
    require(config["paired_bootstrap"] == {
        "confidence_level": 0.95, "resamples": 10000, "seed": 20260830,
    }, "confirmation bootstrap changed")
    require(config["thresholds"] == {
        "function_improvement_minimum": 0.02,
        "function_ci_lower_minimum": 0.0,
        "parse_degradation_maximum": 0.01,
        "apply_degradation_maximum": 0.01,
        "compile_degradation_maximum": 0.01,
        "regression_increase_maximum": 0.01,
        "timeout_increase_maximum": 0.005,
        "file_window_degradation_maximum": 0.03,
    }, "confirmation thresholds changed")


def load_role(spec: dict[str, Any], expected_adapter: str | None) -> dict[str, Any]:
    inference = Path(spec["inference_directory"])
    score = Path(spec["score_directory"])
    predictions = load_jsonl(inference / "predictions.jsonl")
    scores = load_jsonl(score / "scores.jsonl")
    run_manifest = load_json(inference / "run-manifest.json")
    score_manifest = load_json(score / "score-manifest.json")
    generation = load_json(inference / "generation-summary.json")
    summary = load_json(score / "score-summary.json")
    require(len(predictions) == len(scores) == 124, "confirmation denominator must be 124")
    require([x["sample_id"] for x in predictions] == [x["case_id"] for x in scores], "prediction/score order mismatch")
    require(run_manifest["dataset_manifest_sha256"] == MANIFEST_SHA, "confirmation manifest changed")
    require(run_manifest.get("adapter_sha256") == expected_adapter, "model adapter identity changed")
    require(score_manifest["prediction_artifact_sha256"] == sha256_file(inference / "predictions.jsonl"), "score prediction hash mismatch")
    require(score_manifest["execution_artifact_sha256"] == sha256_file(score / "scores.jsonl"), "score execution hash mismatch")
    require(score_manifest["scoring_protocol_version"] == "a3-scoring-v2", "wrong scoring protocol")
    function = [x["success"] for x in scores if x["task_level"] == "function"]
    file_window = [x["success"] for x in scores if x["task_level"] == "file_window"]
    require((len(function), len(file_window)) == (100, 24), "confirmation slice denominator changed")
    violations = []
    if generation["status_counts"].get("ok") != 124:
        violations.append("generation_status_not_all_ok")
    if not generation["determinism_probe_stable"]:
        violations.append("generation_determinism_probe_failed")
    return {
        "inference": inference, "score": score, "predictions": predictions,
        "scores": scores, "summary": summary, "function": function,
        "file_window": file_window, "violations": violations,
    }


def rate(summary: dict[str, Any], key: str) -> float:
    return float(summary["all"]["rates"][key])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "comparison requires clean worktree")
    config = load_json(args.config)
    validate_config(config)
    output = Path(config["output"])
    require(not output.exists(), f"refusing to overwrite comparison: {output}")
    m0 = load_role(config["models"]["m0"], None)
    r2 = load_role(config["models"]["m1_r2"], ADAPTER_SHA)
    prompt_identity = lambda role: [(x["sample_id"], x["prompt_version"], x["prompt_sha256"]) for x in role["predictions"]]
    require(prompt_identity(m0) == prompt_identity(r2), "M0/R2 prompt identity mismatch")

    bootstrap = config["paired_bootstrap"]
    ci = paired_bootstrap_difference(
        m0["function"], r2["function"],
        confidence_level=bootstrap["confidence_level"],
        resamples=bootstrap["resamples"],
        seed=bootstrap["seed"],
    )
    deltas = {
        key: rate(r2["summary"], key) - rate(m0["summary"], key)
        for key in ("parse_success", "apply_success", "compile_success", "regression_failures", "timeouts")
    }
    deltas["file_window_pass_at_1"] = sum(r2["file_window"]) / 24 - sum(m0["file_window"]) / 24
    threshold = config["thresholds"]
    reasons = list(m0["violations"] + r2["violations"])
    if ci["observed"] + 1e-12 < threshold["function_improvement_minimum"]:
        reasons.append("function_improvement_below_threshold")
    if ci["lower"] + 1e-12 < threshold["function_ci_lower_minimum"]:
        reasons.append("function_ci_lower_below_zero")
    for metric in ("parse", "apply", "compile"):
        if deltas[f"{metric}_success"] + 1e-12 < -threshold[f"{metric}_degradation_maximum"]:
            reasons.append(f"{metric}_degradation_exceeded")
    if deltas["regression_failures"] - 1e-12 > threshold["regression_increase_maximum"]:
        reasons.append("regression_increase_exceeded")
    if deltas["timeouts"] - 1e-12 > threshold["timeout_increase_maximum"]:
        reasons.append("timeout_increase_exceeded")
    if deltas["file_window_pass_at_1"] + 1e-12 < -threshold["file_window_degradation_maximum"]:
        reasons.append("file_window_degradation_exceeded")
    result = {
        "version": VERSION,
        "created_at": utc_now(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "config_sha256": sha256_file(args.config),
        "supplementary_confirmation_passed": not reasons,
        "reasons": sorted(set(reasons)),
        "denominators": config["dataset"]["denominators"],
        "counts": {
            "m0": {"function": sum(m0["function"]), "file_window": sum(m0["file_window"]), "all": sum(x["success"] for x in m0["scores"])},
            "m1_r2": {"function": sum(r2["function"]), "file_window": sum(r2["file_window"]), "all": sum(x["success"] for x in r2["scores"])},
        },
        "function_paired_bootstrap": ci,
        "rate_deltas": deltas,
        "artifact_hashes": {
            role: {
                "predictions": sha256_file(data["inference"] / "predictions.jsonl"),
                "scores": sha256_file(data["score"] / "scores.jsonl"),
                "score_summary": sha256_file(data["score"] / "score-summary.json"),
            }
            for role, data in (("m0", m0), ("m1_r2", r2))
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    print(json.dumps({"passed": result["supplementary_confirmation_passed"], "reasons": result["reasons"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
