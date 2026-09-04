"""CPU-only preflight for the frozen Defects4C M0/M1-R2 inference pair."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.external.a3_defects4c_external_common import validate_config, verify_dataset
from scripts.training.a3_formal_common import require, sha256_file, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "external preflight requires a clean worktree")
    require(not args.report.exists(), "refusing to overwrite external preflight report")
    require(args.environment_lock.is_file(), "environment lock missing")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    manifest, prompts = verify_dataset(config)
    model_path = Path(config["model"]["local_path"])
    require(sha256_file(model_path / "config.json") == config["model"]["config_sha256"], "model config hash mismatch")
    require(sha256_file(repo / config["quality_gates"]["path"]) == config["quality_gates"]["sha256"], "quality gate file changed")
    require(sha256_file(repo / config["qualification"]["config"]) == config["qualification"]["config_sha256"], "qualification contract changed")
    require(sha256_file(Path(config["runtime"]["bwrap"])) == config["runtime"]["bwrap_sha256"], "bwrap binary changed")

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False, use_fast=True)
    counts = []
    for prompt in prompts:
        count = len(tokenizer(prompt["prompt_text"], add_special_tokens=True)["input_ids"])
        require(count == prompt["input_tokens"], f"token count changed: {prompt['case_id']}")
        require(count <= config["generation"]["max_input_tokens"], f"prompt too long: {prompt['case_id']}")
        counts.append(count)
    for directory in config["inference"].values():
        require(not Path(directory).exists(), f"external inference output already exists: {directory}")

    report = {
        "version": "a3-defects4c-inference-preflight-v1",
        "status": "passed",
        "checked_at": utc_now(),
        "git_commit": commit,
        "config_sha256": sha256_file(args.config),
        "environment_sha256": sha256_file(args.environment_lock),
        "dataset_manifest_sha256": config["dataset"]["manifest_sha256"],
        "prompts_sha256": config["dataset"]["prompts_sha256"],
        "case_count": manifest["case_count"],
        "min_input_tokens": min(counts),
        "max_input_tokens": max(counts),
        "generation": config["generation"],
        "output_directories_absent": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
