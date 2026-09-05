"""Aggregate all Defects4C qualification checkpoints into a frozen external set."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from scripts.external.qualify_defects4c_case import validate_config
from scripts.training.a3_formal_common import require

SUPPORTED_SUFFIXES = (
    "Please fix bugs in the function and tell me the complete fixed function.",
    "Please provide the correct line following commit message at the infill location.",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def adapted_prompt(source_record: dict[str, Any], source_file: str) -> str:
    messages = source_record["prompt"]
    require([item["role"] for item in messages] == ["system", "user"], "unexpected official prompt roles")
    user = messages[1]["content"].rstrip()
    matching_suffixes = [suffix for suffix in SUPPORTED_SUFFIXES if user.endswith(suffix)]
    require(len(matching_suffixes) == 1, "official prompt suffix changed")
    evidence = user[:-len(matching_suffixes[0])].rstrip()
    return (
        "Repair the localized C++ function described below.\n"
        "Return exactly one pure unified diff and nothing else.\n"
        "Do not use Markdown fences or explanations. Modify only the allowed file.\n"
        "The diff must use these file markers:\n"
        f"--- a/{source_file}\n"
        f"+++ b/{source_file}\n\n"
        f"Allowed file: {source_file}\n"
        f"Benchmark role: {messages[0]['content']}\n\n"
        f"{evidence}\n\n"
        "Unified diff:\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    plan_path = Path(config["source"]["plan"])
    require(sha256_file(plan_path) == config["source"]["plan_sha256"], "source plan hash mismatch")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    records = plan["records"]
    require(len(records) == config["source"]["record_count"], "source record count mismatch")
    official_prompts_path = Path(config["source"]["official_directory"]) / "data/single_function_allinone.saved.jsonl"
    require(sha256_file(official_prompts_path) == config["prompt"]["source_prompt_sha256"], "official prompt hash mismatch")
    prompts_by_idx = {
        item["idx"]: item
        for item in map(json.loads, official_prompts_path.read_text(encoding="utf-8").splitlines())
    }
    model_path = Path(config["prompt"]["model_path"])
    require(sha256_file(model_path / "config.json") == config["prompt"]["model_config_sha256"], "model config hash mismatch")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False, use_fast=True)

    progress = Path(config["progress_directory"])
    decisions = []
    selected = []
    rejection = Counter()
    for index, record in enumerate(records):
        checkpoint_path = progress / "cases" / f"{index:03d}.json"
        require(checkpoint_path.is_file(), f"missing qualification checkpoint: {index}")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        require(checkpoint["identity"]["record"] == record, f"checkpoint record mismatch: {index}")
        require(checkpoint["identity"]["config_sha256"] == sha256_file(args.config), f"checkpoint config mismatch: {index}")
        case = checkpoint.get("case_result")
        qualified = bool(checkpoint.get("qualified") and case)
        reason = None
        prompt = None
        token_count = None
        if qualified:
            prompt = adapted_prompt(prompts_by_idx[record["prompt_idx"]], case["src_file"])
            token_count = len(tokenizer(prompt, add_special_tokens=True)["input_ids"])
            if token_count > config["prompt"]["max_input_tokens"]:
                qualified, reason = False, "prompt_tokens_over_limit"
        else:
            if checkpoint.get("error"):
                reason = "qualification_infrastructure_error"
            elif case and case.get("timed_out"):
                reason = "qualification_timeout"
            elif case and not case.get("fixed_passed"):
                reason = "fixed_tests_not_passed"
            elif case and not case.get("buggy_failed"):
                reason = "buggy_tests_not_failed"
            else:
                reason = "qualification_failed"
        decision = {
            "index": index, "project": record["project"], "commit_after": record["commit_after"],
            "prompt_idx": record["prompt_idx"], "qualified": qualified,
            "reason": reason, "input_tokens": token_count,
        }
        decisions.append(decision)
        if qualified:
            selected.append({
                "case_id": f"d4c-{record['commit_after']}",
                "project": record["project"], "commit_after": record["commit_after"],
                "commit_before": record["commit_before"], "source_file": case["src_file"],
                "prompt_idx": record["prompt_idx"], "prompt_text": prompt,
                "prompt_sha256": sha256_text(prompt), "input_tokens": token_count,
            })
        else:
            rejection[reason] += 1

    report = {
        "version": "a3-defects4c-qualified-v1", "created_at": utc_now(),
        "config_sha256": sha256_file(args.config), "source_plan_sha256": config["source"]["plan_sha256"],
        "evaluated": len(decisions), "qualified": len(selected),
        "minimum_required": config["qualification"]["minimum_qualified"],
        "rejection_counts": dict(sorted(rejection.items())), "decisions": decisions,
    }
    write_json(progress / "aggregation-report.json", report)
    require(len(selected) >= config["qualification"]["minimum_qualified"], f"qualified external denominator below 150: {len(selected)}")
    output = Path(config["output_directory"])
    require(not output.exists(), f"refusing to overwrite qualified external set: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="defects4c-qualified-building-", dir=output.parent))
    try:
        manifest = {
            "version": "a3-defects4c-qualified-v1", "created_at": utc_now(),
            "source_plan_sha256": config["source"]["plan_sha256"],
            "qualification_config_sha256": sha256_file(args.config),
            "source_dataset": "Defects4C", "language": "C++", "task_level": "function",
            "prompt_adapter_version": config["prompt"]["adapter_version"],
            "scoring_protocol": config["prompt"]["scoring_protocol"],
            "minimum_required": config["qualification"]["minimum_qualified"],
            "case_count": len(selected), "repository_family_overlap_with_training": [],
            "cases": selected,
        }
        prompts = [
            {
                "case_id": item["case_id"], "prompt_text": item["prompt_text"],
                "prompt_sha256": item["prompt_sha256"], "input_tokens": item["input_tokens"],
                "source_file": item["source_file"],
            }
            for item in selected
        ]
        write_json(temporary / "manifest.json", manifest)
        (temporary / "prompts.jsonl").write_text(
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in prompts),
            encoding="utf-8",
        )
        shutil.copyfile(progress / "aggregation-report.json", temporary / "qualification-report.json")
        write_json(temporary / "artifact-hashes.json", {
            "manifest.json": sha256_file(temporary / "manifest.json"),
            "prompts.jsonl": sha256_file(temporary / "prompts.jsonl"),
            "qualification-report.json": sha256_file(temporary / "qualification-report.json"),
        })
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"output": str(output), "qualified": len(selected), "manifest_sha256": sha256_file(output / "manifest.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
