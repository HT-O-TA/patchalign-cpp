"""Produce the fail-closed A3 completion ledger without starting A4."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "pre-a4-readiness-v1"
INTERNAL_SHA = "sha256:5425feb24a635cdad734756277680803c984ccb06386f3b91d2379d691b81027"
CONFIRMATION_SHA = "sha256:faca13cc9695c011e19ce1b30a28ce7a02c783b65eec4af07d71aecacf9e6094"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_bound(spec: dict, expected_path: str, expected_sha: str | None = None) -> dict:
    require(spec["path"] == expected_path, f"readiness path changed: {expected_path}")
    require(spec["sha256"].startswith("sha256:") and len(spec["sha256"]) == 71, "readiness hash missing")
    if expected_sha is not None:
        require(spec["sha256"] == expected_sha, f"readiness identity changed: {expected_path}")
    path = Path(spec["path"])
    require(path.is_file(), f"readiness input missing: {path}")
    require(sha256_file(path) == spec["sha256"], f"readiness input hash mismatch: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "readiness finalization requires a clean worktree")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    require(config.get("version") == VERSION, "wrong readiness config version")
    inputs = config["inputs"]
    internal = load_bound(
        inputs["internal"],
        "/mingli01/project/ht/patchalign-cpp/artifacts/a3/sft-r2/comparison-v1/promotion-vs-m0.json",
        INTERNAL_SHA,
    )
    confirmation = load_bound(
        inputs["confirmation"],
        "/mingli01/project/ht/patchalign-cpp/artifacts/a3/confirmation/comparison-v1.json",
        CONFIRMATION_SHA,
    )
    external = load_bound(
        inputs["external"],
        "/mingli01/project/ht/patchalign-cpp/artifacts/a3/defects4c/external-v1/comparison.json",
    )
    require(config["required_gates"] == {
        "internal_gate_passed": True,
        "supplementary_confirmation_passed": True,
        "external_gate_passed": True,
    }, "A4 readiness requirements changed")
    observed = {
        "internal_gate_passed": bool(internal["internal_gate_passed"]),
        "supplementary_confirmation_passed": bool(confirmation["supplementary_confirmation_passed"]),
        "external_gate_passed": bool(external["external_gate_passed"]),
    }
    blockers = [name for name, required in config["required_gates"].items() if observed[name] != required]
    output = Path(config["output"])
    require(output == Path("/mingli01/project/ht/patchalign-cpp/artifacts/a3/pre-a4-readiness-v1.json"), "wrong readiness output")
    require(not output.exists(), "refusing to overwrite readiness ledger")
    result = {
        "version": VERSION,
        "created_at": utc_now(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "config_sha256": sha256_file(args.config),
        "input_hashes": {name: spec["sha256"] for name, spec in inputs.items()},
        "observed_gates": observed,
        "a4_ready": not blockers,
        "blockers": blockers,
        "a4_started": False,
        "decision": "eligible_to_plan_a4" if not blockers else "stop_before_a4",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
