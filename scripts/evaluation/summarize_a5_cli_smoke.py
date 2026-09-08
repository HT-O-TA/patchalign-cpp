#!/usr/bin/env python3
"""Validate and summarize the application-facing final-model CLI smoke."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any

from scripts.evaluation.a5_dpo_final_common import read_json
from scripts.training.a3_formal_common import require, sha256_file, write_json


VERSION = "patchalign-cpp-cli-smoke-v1"


def build_summary(
    config: dict[str, Any],
    comparison: dict[str, Any],
    metadata: dict[str, Any],
    patch_path: Path,
    *,
    job_id: str,
    git_commit: str,
) -> dict[str, Any]:
    require(comparison["version"] == "a5-dpo-final-comparison-v1", "wrong final comparison version")
    recommended = comparison["recommended_model"]
    require(recommended in {"m1_r2", "dpo_beta03"}, "unknown recommended model")
    expected_adapter = (
        comparison["candidate_adapter_sha256"]
        if recommended == "dpo_beta03"
        else comparison["baseline_adapter_sha256"]
    )
    require(metadata["adapter_sha256"] == expected_adapter, "CLI loaded the wrong adapter")
    require(metadata["model_config_sha256"] == config["model"]["config_sha256"], "CLI loaded the wrong Base")
    require(metadata["patch_sha256"] == sha256_file(patch_path), "CLI patch hash mismatch")
    require(metadata["input_tokens"] > 0 and metadata["output_tokens"] > 0, "CLI token counts must be positive")
    require(metadata["latency_seconds"] > 0, "CLI latency must be positive")
    require(metadata["peak_gpu_memory_bytes"] > 0, "CLI peak GPU memory must be positive")
    return {
        "version": VERSION,
        "job_id": job_id,
        "git_commit": git_commit,
        "recommended_model": recommended,
        "model_config_sha256": metadata["model_config_sha256"],
        "adapter_config_sha256": metadata["adapter_config_sha256"],
        "adapter_sha256": metadata["adapter_sha256"],
        "prompt_sha256": metadata["prompt_sha256"],
        "patch_sha256": metadata["patch_sha256"],
        "input_tokens": metadata["input_tokens"],
        "output_tokens": metadata["output_tokens"],
        "latency_seconds": metadata["latency_seconds"],
        "peak_gpu_memory_bytes": metadata["peak_gpu_memory_bytes"],
        "seed": metadata["seed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "refusing to overwrite CLI smoke summary")
    repo = Path(__file__).resolve().parents[2]
    summary = build_summary(
        read_json(args.config),
        read_json(args.comparison),
        read_json(args.metadata),
        args.patch,
        job_id=args.job_id,
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
    )
    write_json(args.output, summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
