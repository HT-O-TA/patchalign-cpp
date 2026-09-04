"""Qualify and freeze the unseen 100/25 A3.4 confirmation set."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator
from transformers import AutoTokenizer

from scripts.data.a2_output_matcher import matcher_metadata
from scripts.data.a2_sandbox_runtime import SANDBOX_VERSION, resolve_bwrap
from scripts.data.qualify_a3_formal_holdout import (
    evaluate_candidate,
    load_cached_evaluations,
    prompt_token_count,
    qualified_count,
    selectable_count,
    sha256_file,
    write_json,
    write_json_atomic,
)


VERSION = "a3-confirmation-v1"
CONFIG_VERSION = "a3-confirmation-qualification-v1"
CANDIDATE_VERSION = "a3-confirmation-candidate-v1"
EXPECTED_CANDIDATE_SHA256 = "bbfc24aae8619cce743cfc37c3ec9ccdbabfe75d528bf551ecc5eb5bbf2b9fe0"
EXPECTED_SOURCE_CONFIG_SHA256 = "61517afa3643ffeb2f4ed5ae1023220ecdfd31766f63d81e21a81d17f9fb49b3"
EXPECTED_MODEL_CONFIG_SHA256 = "4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605"


def strip_prefix(value: str) -> str:
    return value.removeprefix("sha256:")


def validate_config(config: dict[str, Any]) -> None:
    if config.get("version") != CONFIG_VERSION:
        raise RuntimeError("wrong confirmation qualification version")
    candidate = config["candidate"]
    if candidate["manifest_sha256"] != "sha256:" + EXPECTED_CANDIDATE_SHA256:
        raise RuntimeError("confirmation candidate identity changed")
    if candidate["source_config_sha256"] != "sha256:" + EXPECTED_SOURCE_CONFIG_SHA256:
        raise RuntimeError("confirmation source config changed")
    if candidate["task_level_counts"] != {"function": 218, "file_window": 53}:
        raise RuntimeError("confirmation candidate counts changed")
    if config["required_counts"] != {"function": 100, "file_window": 25}:
        raise RuntimeError("confirmation denominator changed")
    model = config["model"]
    if model["model_id"] != "Qwen/Qwen2.5-Coder-7B" or model["revision"] != "0396a76181e127dfc13e5c5ec48a8cee09938b02":
        raise RuntimeError("confirmation tokenizer model changed")
    if model["config_sha256"] != "sha256:" + EXPECTED_MODEL_CONFIG_SHA256:
        raise RuntimeError("confirmation tokenizer config changed")
    expected = {
        "double_replay_required": True,
        "max_input_tokens": 4096,
        "allowed_path": "main.cpp",
        "sandbox_policy_version": "bubblewrap-rootless-v1",
        "output_matcher_version": "runbugrun-legacy-5c023d62",
    }
    if config["qualification"] != expected:
        raise RuntimeError("confirmation qualification policy changed")


def progress_identity(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "a3-confirmation-qualification-progress-v1",
        "config_sha256": "sha256:" + sha256_file(config_path),
        "candidate_manifest_sha256": config["candidate"]["manifest_sha256"],
        "required_task_levels": config["required_counts"],
        "sandbox_policy_version": SANDBOX_VERSION,
        "output_matcher": matcher_metadata(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if args.workers < 1 or args.batch_size < 1:
        raise SystemExit("workers and batch-size must be positive")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    bwrap = resolve_bwrap(args.bwrap)
    candidate_dir = Path(config["candidate"]["directory"])
    progress_dir = Path(config["progress_directory"])
    output_dir = Path(config["output_directory"])
    model_path = Path(config["model"]["path"])
    if output_dir.exists():
        raise RuntimeError(f"refusing to overwrite confirmation set: {output_dir}")
    manifest_path = candidate_dir / "candidate-manifest.json"
    if sha256_file(manifest_path) != EXPECTED_CANDIDATE_SHA256:
        raise RuntimeError("confirmation candidate manifest hash mismatch")
    if sha256_file(model_path / "config.json") != EXPECTED_MODEL_CONFIG_SHA256:
        raise RuntimeError("tokenizer model config hash mismatch")
    candidate_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if candidate_manifest["version"] != CANDIDATE_VERSION:
        raise RuntimeError("wrong confirmation candidate version")
    if candidate_manifest["candidate_task_levels"] != config["candidate"]["task_level_counts"]:
        raise RuntimeError("candidate composition mismatch")
    if candidate_manifest["required_task_levels"] != config["required_counts"]:
        raise RuntimeError("candidate quota mismatch")
    if candidate_manifest["config_sha256"] != config["candidate"]["source_config_sha256"]:
        raise RuntimeError("candidate source config mismatch")
    if candidate_manifest.get("family_exclusion_counts", {}).get("formal_sft", 0) < 1:
        raise RuntimeError("formal SFT family exclusion missing")
    items = candidate_manifest["cases"]
    items_by_order = {item["candidate_order"]: item for item in items}
    if len(items_by_order) != len(items) or len({item["problem_id"] for item in items}) != len(items):
        raise RuntimeError("confirmation candidate families are not unique")

    identity = progress_identity(args.config, config)
    progress_manifest = progress_dir / "progress-manifest.json"
    if progress_manifest.exists():
        if json.loads(progress_manifest.read_text(encoding="utf-8")) != identity:
            raise RuntimeError("confirmation progress identity mismatch")
    else:
        unexpected = [path for path in progress_dir.iterdir()] if progress_dir.exists() else []
        if unexpected:
            raise RuntimeError("non-empty confirmation progress directory without manifest")
        progress_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(progress_manifest, identity)

    evaluations = load_cached_evaluations(progress_dir, items_by_order)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False, use_fast=True)
    prompt_tokens = {
        order: prompt_token_count(candidate_dir, evaluation, tokenizer, config["qualification"]["allowed_path"])
        for order, evaluation in evaluations.items()
        if evaluation["decision"]["qualified"]
    }
    levels = ("function", "file_window")
    by_level = {level: [item for item in items if item["task_level"] == level] for level in levels}
    print(json.dumps({
        "event": "confirmation_qualification_resume",
        "cached": len(evaluations),
        "qualified_by_level": {level: qualified_count(by_level[level], evaluations) for level in levels},
        "selectable_by_level": {level: selectable_count(by_level[level], evaluations, prompt_tokens, 4096) for level in levels},
    }, sort_keys=True), flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for level in levels:
            required = config["required_counts"][level]
            while selectable_count(by_level[level], evaluations, prompt_tokens, 4096) < required:
                pending = [item for item in by_level[level] if item["candidate_order"] not in evaluations][:args.batch_size]
                if not pending:
                    break
                futures = [executor.submit(evaluate_candidate, (str(candidate_dir), item, str(bwrap))) for item in pending]
                for future in as_completed(futures):
                    evaluation = future.result()
                    order = evaluation["decision"]["candidate_order"]
                    write_json_atomic(progress_dir / "evaluations" / f"{order:04d}.json", evaluation)
                    evaluations[order] = evaluation
                    if evaluation["decision"]["qualified"]:
                        prompt_tokens[order] = prompt_token_count(candidate_dir, evaluation, tokenizer, "main.cpp")
                print(json.dumps({
                    "event": "confirmation_batch_complete",
                    "task_level": level,
                    "evaluated": len(evaluations),
                    "qualified": qualified_count(by_level[level], evaluations),
                    "selectable": selectable_count(by_level[level], evaluations, prompt_tokens, 4096),
                    "required": required,
                }, sort_keys=True), flush=True)

    selected_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    decisions: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for order in sorted(evaluations):
        evaluation = evaluations[order]
        decision = dict(evaluation["decision"])
        level = decision["task_level"]
        if decision["qualified"]:
            decision["prompt_tokens"] = prompt_tokens[order]
            if prompt_tokens[order] > 4096:
                decision["qualified"] = False
                decision["reasons"] = [*decision["reasons"], "prompt_tokens_over_limit"]
        if decision["qualified"] and selected_counts[level] < config["required_counts"][level]:
            decision["selected"] = True
            selected.append(evaluation)
            selected_counts[level] += 1
        elif decision["reasons"]:
            rejection_counts.update(decision["reasons"])
        decisions.append(decision)
    if dict(selected_counts) != config["required_counts"]:
        raise RuntimeError(f"candidate pool could not fill confirmation set: {dict(selected_counts)}")

    schema_path = Path(__file__).resolve().parents[2] / "schemas/a2-execution-v0.2.schema.json"
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    for evaluation in selected:
        validator.validate(evaluation["case_result"])
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="a3-confirmation-building-", dir=output_dir.parent))
    try:
        (temporary / "cases").mkdir()
        selected_manifest, selected_results = [], []
        for evaluation in selected:
            item = evaluation["selected_item"]
            source = candidate_dir / "cases" / item["case_id"]
            destination = temporary / "cases" / item["case_id"]
            shutil.copytree(source, destination)
            write_json(destination / "test-partition.json", evaluation["partitions"])
            selected_manifest.append(item)
            selected_results.append(evaluation["case_result"])
        manifest = {
            "version": VERSION,
            "source_candidate_version": CANDIDATE_VERSION,
            "source_candidate_manifest_sha256": "sha256:" + EXPECTED_CANDIDATE_SHA256,
            "qualification_config_sha256": "sha256:" + sha256_file(args.config),
            "task_level_counts": dict(selected_counts),
            "problem_family_unique": True,
            "family_overlap": {"pilot": 0, "formal_sft": 0, "formal_holdout": 0},
            "partition_rule": "F=buggy-fail/fixed-pass; public=stable first ceil(20%) of F; hidden=remaining F; regression=buggy-pass/fixed-pass",
            "output_matcher": matcher_metadata(),
            "prompt_token_policy": {
                "model_config_sha256": "sha256:" + EXPECTED_MODEL_CONFIG_SHA256,
                "input_mode": "raw_completion",
                "allowed_path": "main.cpp",
                "max_input_tokens": 4096,
            },
            "cases": selected_manifest,
        }
        report = {
            "version": VERSION,
            "selected_count": len(selected_manifest),
            "selected_task_levels": dict(selected_counts),
            "evaluated_candidates": len(decisions),
            "unevaluated_candidates": len(items) - len(decisions),
            "qualified_candidates": sum(decision["qualified"] for decision in decisions),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "selected_prompt_token_stats": {
                "count": len(selected_manifest),
                "min": min(decision["prompt_tokens"] for decision in decisions if decision["selected"]),
                "max": max(decision["prompt_tokens"] for decision in decisions if decision["selected"]),
                "total": sum(decision["prompt_tokens"] for decision in decisions if decision["selected"]),
            },
            "workers": args.workers,
            "batch_size": args.batch_size,
            "decisions": decisions,
        }
        write_json(temporary / "confirmation-manifest.json", manifest)
        write_json(temporary / "qualification-report.json", report)
        (temporary / "qualification-results.jsonl").write_text(
            "".join(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n" for result in selected_results),
            encoding="utf-8",
        )
        paths = [temporary / "confirmation-manifest.json", temporary / "qualification-report.json", temporary / "qualification-results.jsonl", *sorted((temporary / "cases").glob("*/*"))]
        (temporary / "sha256sums.txt").write_text(
            "".join(f"{sha256_file(path)}  {path.relative_to(temporary)}\n" for path in paths),
            encoding="utf-8",
        )
        temporary.rename(output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({
        "output": str(output_dir),
        "selected": len(selected),
        "counts": dict(selected_counts),
        "manifest_sha256": "sha256:" + sha256_file(output_dir / "confirmation-manifest.json"),
        "qualification_results_sha256": "sha256:" + sha256_file(output_dir / "qualification-results.jsonl"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
