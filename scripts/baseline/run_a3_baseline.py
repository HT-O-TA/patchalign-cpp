"""Run one frozen A3.0 baseline over the executable A2 holdout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from typing import Any

from jsonschema import Draft202012Validator

from patchalign.evaluation.patches import PatchParseError, parse_unified_diff


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def prompt_sha256(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_prompt(
    case: dict[str, Any], buggy_code: str, public_test: dict[str, Any], allowed_path: str
) -> str:
    return (
        "Repair the localized C++17 program below.\n"
        "Return exactly one pure unified diff and nothing else.\n"
        "Do not use Markdown fences or explanations. Modify only the allowed file.\n"
        "The diff must use these file markers:\n"
        f"--- a/{allowed_path}\n"
        f"+++ b/{allowed_path}\n\n"
        f"Task level: {case['task_level']}\n"
        f"Allowed file: {allowed_path}\n"
        "No natural-language problem statement is available for this executable sample.\n"
        "Use the buggy code and public failing example as evidence.\n\n"
        "Public failing example input:\n"
        "<input>\n"
        f"{public_test['input'].rstrip(chr(10))}\n"
        "</input>\n"
        "Expected output:\n"
        "<output>\n"
        f"{public_test['output'].rstrip(chr(10))}\n"
        "</output>\n\n"
        f"Buggy file {allowed_path}:\n"
        "<code>\n"
        f"{buggy_code.rstrip(chr(10))}\n"
        "</code>\n\n"
        "Unified diff:\n"
    )


def render_model_input(tokenizer: Any, prompt: str, input_mode: str) -> str:
    if input_mode == "raw_completion":
        return prompt
    if input_mode == "chat_non_thinking":
        return tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    raise ValueError(f"unsupported input_mode: {input_mode}")


def load_cases(holdout_dir: Path, allowed_path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((holdout_dir / "a2-manifest.json").read_text(encoding="utf-8"))
    records = []
    for item in manifest["cases"]:
        case_dir = holdout_dir / "cases" / item["case_id"]
        partition = json.loads((case_dir / "test-partition.json").read_text(encoding="utf-8"))
        public_ids = partition["public"]
        if not public_ids:
            raise RuntimeError(f"case has no public test: {item['case_id']}")
        tests = {
            str(test["id"]): test
            for test in map(
                json.loads,
                (case_dir / "tests.jsonl").read_text(encoding="utf-8").splitlines(),
            )
        }
        public_test = tests[str(public_ids[0])]
        buggy_code = (case_dir / "buggy.cpp").read_text(encoding="utf-8")
        records.append(
            {
                "item": item,
                "case_dir": case_dir,
                "prompt": build_prompt(item, buggy_code, public_test, allowed_path),
                "public_test_id": public_ids[0],
            }
        )
    return manifest, records


def git_state(repo: Path) -> tuple[str, bool]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo, text=True
        ).strip()
    )
    return commit, dirty


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def generate_one(
    model: Any,
    tokenizer: Any,
    torch: Any,
    rendered_prompt: str,
    generation: dict[str, Any],
) -> dict[str, Any]:
    encoded = tokenizer(rendered_prompt, return_tensors="pt", add_special_tokens=True)
    input_tokens = int(encoded["input_ids"].shape[1])
    if input_tokens > int(generation["max_input_tokens"]):
        raise RuntimeError(
            f"input token count {input_tokens} exceeds {generation['max_input_tokens']}"
        )
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.monotonic()
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            do_sample=False,
            num_return_sequences=1,
            max_new_tokens=int(generation["max_new_tokens"]),
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )
    torch.cuda.synchronize()
    latency = time.monotonic() - started
    new_ids = generated[0, input_tokens:]
    raw_text = tokenizer.decode(new_ids, skip_special_tokens=True)
    return {
        "raw_text": raw_text,
        "input_tokens": input_tokens,
        "output_tokens": int(new_ids.shape[0]),
        "latency_seconds": latency,
        "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-role", choices=("m0_base", "external"), required=True)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    config = json.loads(args.config.read_text(encoding="utf-8"))
    model_config = config["models"][args.model_role]
    generation = config["generation"]
    if generation != {
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "num_return_sequences": 1,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
    }:
        raise SystemExit("generation configuration does not match frozen A3.0 v1")
    commit, dirty = git_state(repo)
    if dirty:
        raise SystemExit("refusing reportable inference from a dirty worktree")
    if args.output_dir.exists():
        raise SystemExit(f"refusing to overwrite output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True)

    dataset_manifest = args.holdout_dir / "a2-manifest.json"
    dataset_sha = sha256_file(dataset_manifest)
    config_sha = sha256_file(args.config)
    environment_sha = sha256_file(args.environment_lock)
    model_path = Path(model_config["local_path"])
    model_file_sha = sha256_file(model_path / "config.json")
    expected_config = None
    if args.model_role == "m0_base":
        expected_config = "sha256:4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605"
    if expected_config is not None and model_file_sha != expected_config:
        raise SystemExit("M0 model config hash does not match the frozen model identity")

    _, cases = load_cases(args.holdout_dir, config["allowed_path"])
    started_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    run_id = (
        f"{stamp}_a30_{args.model_role}_{config_sha[7:15]}_"
        f"{dataset_sha[7:15]}_s{config['seed']}"
    )
    partial_manifest = {
        "schema_version": "0.1.0",
        "run_id": run_id,
        "stage": "baseline",
        "started_at": started_at,
        "finished_at": None,
        "git_commit": commit,
        "dirty_worktree": False,
        "config_sha256": config_sha,
        "model_id": model_config["model_id"],
        "model_revision": model_config["revision"],
        "model_config_sha256": model_file_sha,
        "adapter_sha256": None,
        "dataset_manifest_sha256": dataset_sha,
        "environment_sha256": environment_sha,
        "seed": int(config["seed"]),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "prediction_artifact_sha256": None,
        "execution_artifact_sha256": None,
        "notes": (
            f"role={args.model_role}; input_mode={model_config['input_mode']}; "
            f"revision_status={model_config['revision_status']}"
        ),
    }
    write_json(args.output_dir / "run-manifest.partial.json", partial_manifest)

    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    prepared = []
    for case in cases:
        rendered = render_model_input(tokenizer, case["prompt"], model_config["input_mode"])
        token_count = len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
        if token_count > generation["max_input_tokens"]:
            raise SystemExit(
                f"prompt too long before model load: {case['item']['case_id']}={token_count}"
            )
        prepared.append({**case, "rendered": rendered, "input_tokens": token_count})

    prompt_records = [
        {
            "case_id": case["item"]["case_id"],
            "task_level": case["item"]["task_level"],
            "prompt_version": config["prompt_version"],
            "prompt_sha256": prompt_sha256(case["prompt"]),
            "prompt_text": case["prompt"],
            "public_test_id": case["public_test_id"],
            "rendered_input_tokens": case["input_tokens"],
        }
        for case in prepared
    ]
    (args.output_dir / "prompts.jsonl").write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in prompt_records
        )
        + "\n",
        encoding="utf-8",
    )

    load_started = time.monotonic()
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.bfloat16,
        device_map={"": 0},
    )
    model.eval()
    load_seconds = time.monotonic() - load_started

    prediction_schema = json.loads(
        (repo / "schemas" / "prediction-v0.1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(prediction_schema)
    records = []
    rendered_by_case = {}
    for index, case in enumerate(prepared, start=1):
        item = case["item"]
        prompt_sha = prompt_sha256(case["prompt"])
        try:
            result = generate_one(
                model, tokenizer, torch, case["rendered"], generation
            )
            raw_text = result["raw_text"]
            try:
                parse_unified_diff(raw_text)
                extracted_patch = raw_text
            except PatchParseError:
                extracted_patch = None
            status = "ok"
            error = None
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            result = {
                "raw_text": "",
                "input_tokens": case["input_tokens"],
                "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch = None
            status = "oom"
            error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            result = {
                "raw_text": "",
                "input_tokens": case["input_tokens"],
                "output_tokens": 0,
                "latency_seconds": 0.0,
                "max_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            }
            extracted_patch = None
            status = "generation_failed"
            error = f"{type(exc).__name__}: {exc}"
        record = {
            "schema_version": "0.1.0",
            "run_id": run_id,
            "sample_id": item["case_id"],
            "model": {
                "model_id": model_config["model_id"],
                "revision": model_config["revision"],
                "config_sha256": model_file_sha,
                "adapter_sha256": None,
            },
            "prompt_version": config["prompt_version"],
            "prompt_sha256": prompt_sha,
            "seed": int(config["seed"]),
            "generation": generation,
            "raw_text": result["raw_text"],
            "extracted_patch": extracted_patch,
            "status": status,
            "error": error,
            "input_tokens": int(result["input_tokens"]),
            "output_tokens": int(result["output_tokens"]),
            "latency_seconds": float(result["latency_seconds"]),
            "max_gpu_memory_bytes": int(result["max_gpu_memory_bytes"]),
        }
        validator.validate(record)
        records.append(record)
        rendered_by_case[item["case_id"]] = case["rendered"]
        print(
            json.dumps(
                {
                    "case": item["case_id"],
                    "index": index,
                    "total": len(prepared),
                    "status": status,
                    "input_tokens": record["input_tokens"],
                    "output_tokens": record["output_tokens"],
                    "latency_seconds": round(record["latency_seconds"], 3),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    probe_count = int(config["determinism_probe_count"])
    probe_records = []
    for record in records[:probe_count]:
        if record["status"] != "ok":
            raise SystemExit(
                f"determinism probe source generation failed: {record['sample_id']}"
            )
        replay = generate_one(
            model,
            tokenizer,
            torch,
            rendered_by_case[record["sample_id"]],
            generation,
        )
        stable = replay["raw_text"] == record["raw_text"]
        probe_records.append(
            {
                "case_id": record["sample_id"],
                "stable": stable,
                "first_sha256": sha256_bytes(record["raw_text"].encode("utf-8")),
                "replay_sha256": sha256_bytes(replay["raw_text"].encode("utf-8")),
            }
        )
        if not stable:
            raise SystemExit(f"nondeterministic generation: {record['sample_id']}")

    predictions_path = args.output_dir / "predictions.jsonl"
    predictions_path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(args.output_dir / "determinism-probe.json", probe_records)
    summary = {
        "version": "a3-baseline-generation-v1",
        "run_id": run_id,
        "model_role": args.model_role,
        "cases": len(records),
        "status_counts": {
            status: sum(record["status"] == status for record in records)
            for status in ("ok", "generation_failed", "timeout", "oom")
        },
        "strict_diff_count": sum(record["extracted_patch"] is not None for record in records),
        "input_tokens": sum(record["input_tokens"] for record in records),
        "output_tokens": sum(record["output_tokens"] for record in records),
        "generation_seconds": sum(record["latency_seconds"] for record in records),
        "model_load_seconds": load_seconds,
        "peak_gpu_memory_bytes": max(
            (record["max_gpu_memory_bytes"] or 0) for record in records
        ),
        "determinism_probe_count": probe_count,
        "determinism_probe_stable": all(item["stable"] for item in probe_records),
    }
    write_json(args.output_dir / "generation-summary.json", summary)

    manifest = {
        **partial_manifest,
        "finished_at": utc_now(),
        "prediction_artifact_sha256": sha256_file(predictions_path),
        "notes": (
            partial_manifest["notes"]
            + f"; prompts_sha256={sha256_file(args.output_dir / 'prompts.jsonl')}; "
            + f"generation_summary_sha256={sha256_file(args.output_dir / 'generation-summary.json')}"
        ),
    }
    manifest_schema = json.loads(
        (repo / "schemas" / "run-manifest-v0.1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        manifest_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(manifest)
    write_json(args.output_dir / "run-manifest.json", manifest)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
