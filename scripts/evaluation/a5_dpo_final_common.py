"""Fail-closed helpers for the selected A5 DPO final evaluation."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file


VERSION = "a5-dpo-final-eval-v1"
DATASETS = ("formal", "confirmation", "defects4c")
MODEL_REVISION = "0396a76181e127dfc13e5c5ec48a8cee09938b02"
SELECTED_ADAPTER_SHA = "sha256:2de1cb5bf0100aeba384b8cfb52fae990a77d5971d1b595cb698659f66f0683a"
BASELINE_ADAPTER_SHA = "sha256:8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(repo: Path, config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong A5 final evaluation version")
    require(config.get("seed") == 20260830, "wrong A5 final seed")
    require(config["selection"]["selected"] == "beta03", "wrong selected DPO role")
    require(config["selection"]["sha256"] == "sha256:248ad6dcb6783fd2e8c971b05191a87c5b5bd02b696e26f7076262631de665f4", "selection identity changed")
    require(sha256_file(repo / config["selection"]["decision"]) == config["selection"]["decision_sha256"], "selection ADR changed")
    require(config["model"] == {
        "model_id": "Qwen/Qwen2.5-Coder-7B",
        "local_path": "/mingli01/models/Qwen2.5-Coder-7B",
        "revision": MODEL_REVISION,
        "config_sha256": "sha256:4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605",
    }, "base model identity changed")
    require(config["adapter"]["sha256"] == SELECTED_ADAPTER_SHA, "selected adapter changed")
    require(config["adapter"]["source_adapter_sha256"] == BASELINE_ADAPTER_SHA, "DPO source adapter changed")
    require(config["generation"] == {
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "num_return_sequences": 1,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
        "determinism_probe_count": 3,
    }, "A5 final generation policy changed")
    expected = {
        "formal": ("cpp", 500, {"function": 400, "file_window": 100}, "sha256:5c438d36a0d4efc833dd6d0d26c67a1579f2c2e26de13f42ce01a809c07c3386"),
        "confirmation": ("cpp", 124, {"function": 100, "file_window": 24}, "sha256:7adf960fff4e7f1ee3ca95539ffa1196c3421805659c94bb46a29d0022690917"),
        "defects4c": ("defects4c", 176, None, "sha256:0728c6028328adfecb968e42351c909f4ea95a24f24a0e355d2739e97b028631"),
    }
    require(tuple(config["datasets"]) == DATASETS, "A5 final dataset set/order changed")
    for name, (kind, count, levels, manifest_sha) in expected.items():
        dataset = config["datasets"][name]
        require(dataset["kind"] == kind and dataset["case_count"] == count, f"{name} denominator changed")
        require(dataset["manifest_sha256"] == manifest_sha, f"{name} manifest identity changed")
        if levels is not None:
            require(dataset["task_level_counts"] == levels, f"{name} task mix changed")
            require(dataset["allowed_path"] == "main.cpp", f"{name} allowed path changed")
            require(dataset["prompt_version"] == "a3-cpp-repair-v1", f"{name} prompt version changed")
        require(dataset["baseline"]["adapter_sha256"] == BASELINE_ADAPTER_SHA, f"{name} baseline changed")
    require(config["scoring"] == {
        "protocol": "a3-scoring-v2",
        "config": "configs/evaluation/a3_scoring_v2.json",
        "config_sha256": "sha256:b8d9507ec7fc97c370e52230759e0b2b84591d6fb4200a50944add19ebe859e8",
        "bwrap": "/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap",
        "bwrap_sha256": "sha256:c69d2514ecdcbb927af4129caccceb8bfc122954e59ab8aa6f9ec50e9a09afda",
    }, "A5 final scoring contract changed")
    require(config["environment"]["lock_sha256"] == "sha256:bef5b08f129a08a1f720e8698c99606832192d1f77b0f9cce1adc98e3baa43a4", "environment identity changed")


def verify_selection_and_adapter(config: dict[str, Any]) -> dict[str, Any]:
    selection_path = Path(config["selection"]["path"])
    require(sha256_file(selection_path) == config["selection"]["sha256"], "DPO selection artifact changed")
    selection = read_json(selection_path)
    require(selection["selected"] == config["selection"]["selected"], "selected role mismatch")
    require(selection["selected_is_promotable"] is True, "selected DPO was not promotable")
    adapter = config["adapter"]
    adapter_path = Path(adapter["path"])
    require(sha256_file(adapter_path / "adapter_model.safetensors") == adapter["sha256"], "selected adapter weights changed")
    require(sha256_file(adapter_path / "adapter_config.json") == adapter["config_sha256"], "selected adapter config changed")
    require(sha256_file(Path(adapter["training_manifest"])) == adapter["training_manifest_sha256"], "DPO training manifest changed")
    require(sha256_file(Path(adapter["training_summary"])) == adapter["training_summary_sha256"], "DPO training summary changed")
    manifest = read_json(Path(adapter["training_manifest"]))
    summary = read_json(Path(adapter["training_summary"]))
    require(manifest["variant"] == {"name": "beta03", "role": "control", "beta": 0.3}, "DPO variant changed")
    require(manifest["adapter_sha256"] == summary["adapter_sha256"] == adapter["sha256"], "DPO adapter binding changed")
    require(manifest["source_adapter_sha256"] == adapter["source_adapter_sha256"], "DPO source binding changed")
    require(summary["status"] == "completed" and summary["pairs"] == 175 and summary["optimizer_steps"] == 44, "DPO training completion changed")
    return selection


def verify_dataset(config: dict[str, Any], name: str) -> tuple[Path, dict[str, Any]]:
    require(name in DATASETS, f"unknown final dataset: {name}")
    dataset = config["datasets"][name]
    root = Path(dataset["root"])
    manifest_path = root / dataset["manifest"]
    require(sha256_file(manifest_path) == dataset["manifest_sha256"], f"{name} manifest changed")
    manifest = read_json(manifest_path)
    cases = manifest["cases"]
    require(len(cases) == dataset["case_count"], f"{name} denominator changed")
    if dataset["kind"] == "cpp":
        require(Counter(row["task_level"] for row in cases) == dataset["task_level_counts"], f"{name} task mix changed")
    else:
        require(manifest["case_count"] == dataset["case_count"], "Defects4C manifest count changed")
        require(sha256_file(root / dataset["prompts"]) == dataset["prompt_artifact_sha256"], "Defects4C prompts changed")
    return root, manifest


def verify_baseline(config: dict[str, Any], name: str) -> None:
    baseline = config["datasets"][name]["baseline"]
    inference = Path(baseline["inference_directory"])
    scoring = Path(baseline["scoring_directory"])
    files = {
        inference / "predictions.jsonl": baseline["predictions_sha256"],
        inference / "run-manifest.json": baseline["run_manifest_sha256"],
        inference / "generation-summary.json": baseline["generation_summary_sha256"],
    }
    if name == "defects4c":
        files[scoring / "scores-m1_r2.jsonl"] = baseline["scores_sha256"]
        files[scoring / "summary-m1_r2.json"] = baseline["score_summary_sha256"]
    else:
        files[scoring / "scores.jsonl"] = baseline["scores_sha256"]
        files[scoring / "score-summary.json"] = baseline["score_summary_sha256"]
        files[scoring / "score-manifest.json"] = baseline["score_manifest_sha256"]
    for path, expected in files.items():
        require(sha256_file(path) == expected, f"{name} baseline artifact changed: {path.name}")


def inference_dir(config: dict[str, Any], name: str) -> Path:
    return Path(config["outputs"]["root"]) / name / "inference"


def scoring_dir(config: dict[str, Any], name: str) -> Path:
    return Path(config["outputs"]["root"]) / name / "scoring"
