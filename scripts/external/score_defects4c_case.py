"""Score both frozen model predictions for one qualified Defects4C case."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from patchalign.evaluation.patches import (
    PatchParseError,
    PatchPolicyError,
    enforce_patch_policy,
    normalize_terminal_lf,
    parse_unified_diff,
)
from scripts.external.a3_defects4c_external_common import (
    load_json,
    sha256_text,
    validate_config,
    verify_dataset,
    verify_predictions,
)
from scripts.training.a3_formal_common import require, sha256_file, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_result(output: str) -> dict:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("version") == "a3-defects4c-prediction-case-v1":
            return value
    raise RuntimeError("rootfs prediction runner did not emit a case result")


def early_result(role: str, prediction: dict, classification: str, reason: str) -> dict:
    raw_text = prediction["raw_text"]
    return {
        "version": "a3-defects4c-score-case-v1",
        "role": role,
        "case_id": prediction["sample_id"],
        "prediction_status": prediction["status"],
        "raw_prediction_sha256": sha256_text(raw_text),
        "evaluated_patch_sha256": None,
        "transport_normalization": None,
        "terminal_classification": classification,
        "success": False,
        "timed_out": False,
        "reason": reason,
        "rootfs_result": None,
    }


def score_role(config: dict, case: dict, role: str, prediction: dict, repo: Path) -> dict:
    if prediction["status"] != "ok":
        return early_result(role, prediction, "generation_failed", prediction.get("error") or prediction["status"])
    evaluated, added = normalize_terminal_lf(prediction["raw_text"])
    base = {
        "version": "a3-defects4c-score-case-v1",
        "role": role,
        "case_id": case["case_id"],
        "prediction_status": prediction["status"],
        "raw_prediction_sha256": sha256_text(prediction["raw_text"]),
        "evaluated_patch_sha256": sha256_text(evaluated),
        "transport_normalization": {
            "rule": "append_one_lf_if_nonempty_and_missing",
            "terminal_lf_added": added,
            "added_bytes": int(added),
        },
        "success": False,
        "timed_out": False,
        "rootfs_result": None,
    }
    try:
        parsed = parse_unified_diff(evaluated)
    except PatchParseError as exc:
        return {**base, "terminal_classification": "parse_failed", "reason": str(exc)}
    try:
        changed = enforce_patch_policy(parsed, [case["source_file"]])
    except PatchPolicyError as exc:
        return {**base, "terminal_classification": "policy_violation", "reason": str(exc)}
    require(changed == (case["source_file"],), "unexpected external changed path order")

    scoring = config["scoring"]
    patch_dir = Path(config["qualification"]["checkout_directory"]) / ".patchalign-score-patches" / role
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"{case['commit_after']}.patch"
    patch_path.write_text(evaluated, encoding="utf-8")
    inside_patch = Path("/out") / patch_path.relative_to(config["qualification"]["checkout_directory"])
    runtime = config["runtime"]
    command = [
        runtime["bwrap"], "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
        "--bind", runtime["rootfs_directory"], "/",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/root", "--dir", "/tmp/home",
        "--ro-bind", config["qualification"]["official_directory"], "/src",
        "--bind", config["qualification"]["checkout_directory"], "/out",
        "--ro-bind", runtime["conda_environment"], "/opt/host-conda",
        "--ro-bind", str(repo), "/patchalign",
        "--remount-ro", "/",
        "--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/host-conda/bin",
        "--setenv", "HOME", "/tmp/home", "--setenv", "PYTHONNOUSERSITE", "1", "--setenv", "LC_ALL", "C.UTF-8",
        "--chdir", "/patchalign",
        "/opt/host-conda/bin/python", "scripts/external/run_defects4c_prediction_case.py",
        "--project", case["project"], "--sha", case["commit_after"],
        "--source-file", case["source_file"], "--patch", str(inside_patch), "--role", role,
        "--cpu-count", str(scoring["cpu_count_per_case"]),
        "--timeout-seconds", str(scoring["timeout_seconds"]),
    ]
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=scoring["timeout_seconds"] + 120,
        )
        rootfs_result = parse_result(completed.stdout)
        classification = rootfs_result["terminal_classification"]
        return {
            **base,
            "terminal_classification": classification,
            "success": bool(completed.returncode == 0 and rootfs_result["success"]),
            "timed_out": bool(rootfs_result["timed_out"]),
            "bwrap_returncode": completed.returncode,
            "output_tail": completed.stdout[-4000:],
            "rootfs_result": rootfs_result,
        }
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return {
            **base,
            "terminal_classification": "scoring_timeout",
            "success": False,
            "timed_out": True,
            "output_tail": output[-4000:],
        }
    finally:
        patch_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index", type=int, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "external scorer requires a clean worktree")
    config = load_json(args.config)
    validate_config(config)
    manifest, _ = verify_dataset(config)
    require(0 <= args.index < len(manifest["cases"]), "external score index outside frozen denominator")
    case = manifest["cases"][args.index]
    role_data = {}
    for role in ("m0", "m1_r2"):
        directory, predictions, run_manifest = verify_predictions(config, role)
        require(predictions[args.index]["sample_id"] == case["case_id"], f"{role} prediction order mismatch")
        role_data[role] = {
            "directory": directory,
            "prediction": predictions[args.index],
            "prediction_sha256": run_manifest["prediction_artifact_sha256"],
        }
    identity = {
        "version": "a3-defects4c-score-case-v1",
        "index": args.index,
        "case": case,
        "config_sha256": sha256_file(args.config),
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "prediction_sha256": {role: data["prediction_sha256"] for role, data in role_data.items()},
    }
    checkpoint = Path(config["scoring"]["progress_directory"]) / "cases" / f"{args.index:03d}.json"
    if checkpoint.exists():
        cached = load_json(checkpoint)
        require(cached["identity"] == identity, "external score checkpoint identity changed")
        print(json.dumps(cached, ensure_ascii=False, sort_keys=True))
        return
    results = {
        role: score_role(config, case, role, data["prediction"], repo)
        for role, data in role_data.items()
    }
    payload = {"identity": identity, "finished_at": utc_now(), "results": results}
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    write_json(checkpoint.with_suffix(".json.tmp"), payload)
    checkpoint.with_suffix(".json.tmp").replace(checkpoint)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
