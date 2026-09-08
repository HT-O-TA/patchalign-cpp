from __future__ import annotations

from pathlib import Path

import pytest

from scripts.evaluation.summarize_a5_cli_smoke import build_summary
from scripts.training.a3_formal_common import sha256_file


def fixtures(tmp_path: Path) -> tuple[dict, dict, dict, Path]:
    patch = tmp_path / "candidate.patch"
    patch.write_text("--- a/main.cpp\n+++ b/main.cpp\n@@ -1 +1 @@\n-old\n+new\n", encoding="utf-8")
    config = {"model": {"config_sha256": "sha256:base"}}
    comparison = {
        "version": "a5-dpo-final-comparison-v1",
        "recommended_model": "m1_r2",
        "baseline_adapter_sha256": "sha256:baseline",
        "candidate_adapter_sha256": "sha256:candidate",
    }
    metadata = {
        "model_config_sha256": "sha256:base",
        "adapter_config_sha256": "sha256:adapter-config",
        "adapter_sha256": "sha256:baseline",
        "prompt_sha256": "sha256:prompt",
        "patch_sha256": sha256_file(patch),
        "input_tokens": 10,
        "output_tokens": 20,
        "latency_seconds": 1.25,
        "peak_gpu_memory_bytes": 1024,
        "seed": 20260830,
    }
    return config, comparison, metadata, patch


def test_build_summary_binds_recommended_model_and_patch(tmp_path: Path) -> None:
    config, comparison, metadata, patch = fixtures(tmp_path)
    result = build_summary(config, comparison, metadata, patch, job_id="123", git_commit="abc")
    assert result["version"] == "patchalign-cpp-cli-smoke-v1"
    assert result["recommended_model"] == "m1_r2"
    assert result["adapter_sha256"] == "sha256:baseline"
    assert result["patch_sha256"] == sha256_file(patch)


def test_build_summary_rejects_wrong_adapter(tmp_path: Path) -> None:
    config, comparison, metadata, patch = fixtures(tmp_path)
    metadata["adapter_sha256"] = "sha256:candidate"
    with pytest.raises(RuntimeError, match="wrong adapter"):
        build_summary(config, comparison, metadata, patch, job_id="123", git_commit="abc")


def test_build_summary_rejects_changed_patch(tmp_path: Path) -> None:
    config, comparison, metadata, patch = fixtures(tmp_path)
    patch.write_text("changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="patch hash mismatch"):
        build_summary(config, comparison, metadata, patch, job_id="123", git_commit="abc")
