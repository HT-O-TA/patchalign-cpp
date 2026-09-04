"""Fail-closed bindings shared by the frozen A3.4 Defects4C evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file
from scripts.training.a3_sft_r2_inference_common import verify_training_artifact


VERSION = "a3-defects4c-external-v1"
MODEL_REVISION = "0396a76181e127dfc13e5c5ec48a8cee09938b02"
MODEL_CONFIG_SHA = "sha256:4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605"
ADAPTER_SHA = "sha256:8437acca7208ffc984b739a1f965c253899f7c8462a21b6af10c1c6dd153425a"
QUALITY_GATE_SHA = "sha256:6ba153f1ec3d56a41eab0048595a5169816df5e404a37c44c3097b7f375f5af1"
QUALIFICATION_CONFIG_SHA = "sha256:760f81a197a8265de1c76e9ec6b2b8679432cf04396c2fce153ddf796bf0cd0c"
ROOTFS_SHA = "sha256:46d659c0f3dac1acb0849a17fd0cae2a18848f357847f3db2b61a5858f8f1bab"
BWRAP_SHA = "sha256:c69d2514ecdcbb927af4129caccceb8bfc122954e59ab8aa6f9ec50e9a09afda"


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong external evaluation version")
    require(config.get("run_id") == "a34_defects4c_s20260830", "wrong external run id")
    require(config.get("seed") == 20260830, "wrong external seed")
    model = config["model"]
    require(model == {
        "model_id": "Qwen/Qwen2.5-Coder-7B",
        "local_path": "/mingli01/models/Qwen2.5-Coder-7B",
        "revision": MODEL_REVISION,
        "config_sha256": MODEL_CONFIG_SHA,
    }, "external model identity changed")
    source = config["source_training"]
    require(source["adapter_sha256"] == ADAPTER_SHA, "external adapter identity changed")
    verify_training_artifact(config)

    dataset = config["dataset"]
    require(dataset["root"] == "/mingli01/data/patchalign-cpp/external/defects4c/qualified-v1", "wrong external dataset root")
    require(dataset["manifest"] == "manifest.json", "wrong external manifest name")
    require(dataset["prompts"] == "prompts.jsonl", "wrong external prompts name")
    require(150 <= dataset["case_count"] <= 203, "external denominator outside frozen bounds")
    for key in ("manifest_sha256", "prompts_sha256"):
        require(dataset[key].startswith("sha256:") and len(dataset[key]) == 71, f"missing dataset hash: {key}")

    require(config["generation"] == {
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "num_return_sequences": 1,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
    }, "external generation settings changed")
    require(config["input_mode"] == "raw_completion", "external input mode changed")
    require(config["prompt_version"] == "a3-defects4c-unified-diff-v1", "external prompt version changed")
    require(config["inference"] == {
        "m0": "/mingli01/project/ht/patchalign-cpp/artifacts/a3/defects4c/inference-m0",
        "m1_r2": "/mingli01/project/ht/patchalign-cpp/artifacts/a3/defects4c/inference-m1_r2",
    }, "external inference directories changed")

    qualification = config["qualification"]
    require(qualification["config"] == "configs/external/a3_defects4c_qualification_v1.json", "wrong qualification config")
    require(qualification["config_sha256"] == QUALIFICATION_CONFIG_SHA, "qualification config identity changed")
    require(qualification["checkout_directory"] == "/mingli01/data/patchalign-cpp/external/defects4c/runtime/out", "wrong checkout root")
    require(qualification["official_directory"] == "/mingli01/data/patchalign-cpp/external/defects4c/source/defectsc_tpl", "wrong official source root")
    runtime = config["runtime"]
    require(runtime["rootfs_directory"] == "/mingli01/data/patchalign-cpp/external/defects4c/rootfs-cb4efcac", "wrong rootfs directory")
    require(runtime["rootfs_archive_sha256"] == ROOTFS_SHA, "rootfs identity changed")
    require(runtime["bwrap"] == "/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap", "wrong bwrap path")
    require(runtime["bwrap_sha256"] == BWRAP_SHA, "bwrap identity changed")
    require(runtime["conda_environment"] == "/mingli01/project/ht/.conda_envs/patchalign-cpp", "wrong conda environment")

    scoring = config["scoring"]
    require(scoring["protocol"] == "a3-scoring-v2", "wrong external scoring protocol")
    require(scoring["apply_command"] == ["git", "apply", "--recount"], "external apply semantics changed")
    require(scoring["cpu_count_per_case"] == 8, "external scoring CPU count changed")
    require(scoring["timeout_seconds"] == 5400, "external scoring timeout changed")
    require(scoring["network"] == "unshared", "external scorer network boundary changed")
    require(scoring["sanitizer"] == "only_if_official_metadata_applies", "external sanitizer policy changed")
    require(scoring["progress_directory"] == "/mingli01/data/patchalign-cpp/external/defects4c/runtime/scoring-progress-v1", "wrong scoring progress directory")
    require(scoring["output_directory"] == "/mingli01/project/ht/patchalign-cpp/artifacts/a3/defects4c/external-v1", "wrong external output directory")
    quality = config["quality_gates"]
    require(quality == {
        "path": "configs/evaluation/quality_gates_v1.json",
        "sha256": QUALITY_GATE_SHA,
        "external_pass_at_1_maximum_degradation": 0.02,
    }, "external quality gate changed")


def verify_dataset(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dataset = config["dataset"]
    root = Path(dataset["root"])
    manifest_path = root / dataset["manifest"]
    prompts_path = root / dataset["prompts"]
    require(sha256_file(manifest_path) == dataset["manifest_sha256"], "qualified manifest hash mismatch")
    require(sha256_file(prompts_path) == dataset["prompts_sha256"], "qualified prompts hash mismatch")
    manifest = load_json(manifest_path)
    prompts = load_jsonl(prompts_path)
    require(manifest["version"] == "a3-defects4c-qualified-v1", "wrong qualified manifest version")
    require(manifest["case_count"] == dataset["case_count"], "qualified denominator changed")
    require(manifest["repository_family_overlap_with_training"] == [], "external/train overlap detected")
    require(len(manifest["cases"]) == len(prompts) == dataset["case_count"], "qualified artifact count mismatch")
    ids = [case["case_id"] for case in manifest["cases"]]
    require(ids == [prompt["case_id"] for prompt in prompts], "qualified prompt order mismatch")
    for case, prompt in zip(manifest["cases"], prompts, strict=True):
        require(case["prompt_sha256"] == prompt["prompt_sha256"] == sha256_text(prompt["prompt_text"]), "qualified prompt identity changed")
        require(case["source_file"] == prompt["source_file"], "qualified source path changed")
    return manifest, prompts


def verify_predictions(config: dict[str, Any], role: str) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    require(role in {"m0", "m1_r2"}, "unknown external role")
    directory = Path(config["inference"][role])
    predictions_path = directory / "predictions.jsonl"
    run_manifest_path = directory / "run-manifest.json"
    require(predictions_path.is_file() and run_manifest_path.is_file(), f"missing {role} inference artifacts")
    predictions = load_jsonl(predictions_path)
    run_manifest = load_json(run_manifest_path)
    expected_adapter = None if role == "m0" else ADAPTER_SHA
    require(run_manifest["adapter_sha256"] == expected_adapter, f"{role} adapter mismatch")
    require(run_manifest["dataset_manifest_sha256"] == config["dataset"]["manifest_sha256"], f"{role} dataset mismatch")
    require(run_manifest["prediction_artifact_sha256"] == sha256_file(predictions_path), f"{role} prediction hash mismatch")
    require(len(predictions) == config["dataset"]["case_count"], f"{role} prediction count mismatch")
    return directory, predictions, run_manifest
