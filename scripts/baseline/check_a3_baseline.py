"""CPU-only fail-closed preflight for the frozen A3.0 baseline jobs."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.baseline.run_a3_baseline import load_cases, render_model_input
from scripts.baseline.score_a3_baseline import score_prediction
from scripts.data.a2_sandbox_runtime import resolve_bwrap


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def gold_prediction(
    item: dict[str, Any], case_dir: Path, model: dict[str, Any]
) -> dict[str, Any]:
    buggy = (case_dir / "buggy.cpp").read_text(encoding="utf-8").splitlines(keepends=True)
    fixed = (case_dir / "fixed.cpp").read_text(encoding="utf-8").splitlines(keepends=True)
    patch = "".join(
        difflib.unified_diff(
            buggy,
            fixed,
            fromfile="a/main.cpp",
            tofile="b/main.cpp",
        )
    )
    return {
        "sample_id": item["case_id"],
        "status": "ok",
        "raw_text": patch,
        "model": model,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, required=True)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    bwrap = resolve_bwrap(args.bwrap)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    frozen_generation = {
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "num_return_sequences": 1,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
    }
    if config["generation"] != frozen_generation:
        raise SystemExit("unexpected A3.0 generation configuration")
    manifest, cases = load_cases(args.holdout_dir, config["allowed_path"])
    if manifest["task_level_counts"] != {"function": 50, "file_window": 20}:
        raise SystemExit("A2 holdout composition changed")
    token_stats = {}
    for role, model in config["models"].items():
        model_path = Path(model["local_path"])
        if not model_path.is_dir():
            raise SystemExit(f"missing model directory: {model_path}")
        tokenizer = AutoTokenizer.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=False
        )
        counts = []
        for case in cases:
            rendered = render_model_input(tokenizer, case["prompt"], model["input_mode"])
            counts.append(
                len(tokenizer(rendered, add_special_tokens=True)["input_ids"])
            )
        if max(counts) > config["generation"]["max_input_tokens"]:
            raise SystemExit(f"{role} prompt exceeds frozen token budget")
        token_stats[role] = {
            "min": min(counts),
            "max": max(counts),
            "total": sum(counts),
            "model_config_sha256": sha256_file(model_path / "config.json"),
        }

    first = cases[0]
    item = first["item"]
    prediction = gold_prediction(item, first["case_dir"], config["models"]["m0_base"])
    score = score_prediction(item, first["case_dir"], prediction, bwrap)
    if not score["success"]:
        raise SystemExit(
            "gold patch sandbox score failed: "
            + json.dumps(score, ensure_ascii=False, sort_keys=True)
        )
    print(
        json.dumps(
            {
                "cases": len(cases),
                "gold_patch_score": score["terminal_classification"],
                "prompt_tokens": token_stats,
                "status": "passed",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
