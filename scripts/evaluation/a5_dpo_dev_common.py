"""Frozen input and selection helpers for A5 DPO development evaluation."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from scripts.training.a3_formal_common import require, sha256_file


VERSION = "a5-dpo-dev-v1"
ROLES = ("baseline", "beta01", "beta03")
PERFORMANCE_KEYS = (
    "pass_count",
    "hidden_test_success",
    "public_test_success",
    "compile_success",
    "apply_success",
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate_config(repo: Path, config: dict[str, Any]) -> None:
    require(config.get("version") == VERSION, "wrong A5 dev config version")
    require(config.get("seed") == 20260830, "wrong A5 dev seed")
    contract = config["contract"]
    require(sha256_file(repo / contract["training_config"]) == contract["training_config_sha256"], "DPO training config changed")
    require(sha256_file(repo / contract["selection_decision"]) == contract["selection_decision_sha256"], "DPO selection ADR changed")
    require(config["dataset"] == {
        "root": "/mingli01/data/patchalign-cpp/data-v2/dev-exec-v1",
        "manifest": "dev-exec-manifest.json",
        "manifest_sha256": "sha256:457318d186ba056a970ac917f4161cacf98b07f2bd121327452a5eaaf601340f",
        "case_count": 64,
        "task_level_counts": {"function": 64},
        "source_split": "train",
        "a4_training_overlap": 0,
        "problem_family_unique": True,
    }, "A5 dev dataset changed")
    require(config["inference"] == {
        "prompt_version": "a5-dev-cpp-repair-v1",
        "input_mode": "raw_completion",
        "allowed_path": "main.cpp",
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "num_return_sequences": 1,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
        "determinism_probe_count": 3,
    }, "A5 dev inference policy changed")
    require(config["selection"] == {
        "baseline": "baseline",
        "candidates": ["beta01", "beta03"],
        "priority": [
            "pass_count_desc",
            "hidden_test_success_desc",
            "public_test_success_desc",
            "compile_success_desc",
            "apply_success_desc",
        ],
        "non_degradation_constraints": [
            "timeouts_not_above_baseline",
            "regression_failures_not_above_baseline",
        ],
        "positive_signal": "strict_lexicographic_improvement_over_baseline",
        "fallback_risk_order": [
            "regression_failures_asc",
            "timeouts_asc",
            "performance_priority_desc",
            "beta03_on_exact_tie",
        ],
    }, "A5 dev selection policy changed")


def verify_dataset(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    dataset = config["dataset"]
    root = Path(dataset["root"])
    manifest_path = root / dataset["manifest"]
    require(sha256_file(manifest_path) == dataset["manifest_sha256"], "A5 dev manifest changed")
    manifest = read_json(manifest_path)
    require(manifest["selected_count"] == dataset["case_count"], "A5 dev denominator changed")
    require(Counter(row["task_level"] for row in manifest["cases"]) == dataset["task_level_counts"], "A5 dev task mix changed")
    require(all(row["upstream_split"] == dataset["source_split"] for row in manifest["cases"]), "A5 dev split changed")
    require(manifest["a4_selected_overlap"] == dataset["a4_training_overlap"], "A5 dev/A4 overlap changed")
    require(manifest["problem_family_unique"] is dataset["problem_family_unique"], "A5 dev family uniqueness changed")
    return root, manifest


def resolve_adapter(config: dict[str, Any], role: str) -> dict[str, Any]:
    require(role in ROLES, f"unknown A5 dev role: {role}")
    if role == "baseline":
        source = config["models"]["baseline"]
        adapter = Path(source["adapter_path"])
        require(sha256_file(adapter / "adapter_model.safetensors") == source["adapter_sha256"], "baseline adapter changed")
        require(sha256_file(adapter / "adapter_config.json") == source["adapter_config_sha256"], "baseline adapter config changed")
        require(sha256_file(Path(source["training_manifest"])) == source["training_manifest_sha256"], "baseline manifest changed")
        return {
            "role": role,
            "stage": "sft",
            "adapter_path": str(adapter),
            "adapter_sha256": source["adapter_sha256"],
            "training_manifest_sha256": source["training_manifest_sha256"],
        }

    expected = config["models"]["dpo_variants"][role]
    training_dir = Path(config["models"]["dpo_training_root"]) / role
    manifest_path = training_dir / "training-manifest.json"
    summary_path = training_dir / "training-summary.json"
    manifest = read_json(manifest_path)
    summary = read_json(summary_path)
    require(manifest["stage"] == "dpo" and manifest["variant"] == {"name": role, **expected}, "wrong DPO variant manifest")
    require(manifest["git_commit"] == config["models"]["dpo_training_git_commit"], "DPO training commit changed")
    require(manifest["config_sha256"] == config["contract"]["training_config_sha256"], "DPO config binding changed")
    require(manifest["source_adapter_sha256"] == config["models"]["baseline"]["adapter_sha256"], "DPO source adapter changed")
    require(manifest["execution_artifact_sha256"] == sha256_file(summary_path), "DPO summary binding changed")
    adapter = training_dir / "final-adapter"
    require(sha256_file(adapter / "adapter_model.safetensors") == manifest["adapter_sha256"] == summary["adapter_sha256"], "DPO adapter binding changed")
    require(sha256_file(adapter / "adapter_config.json") == summary["adapter_config_sha256"], "DPO adapter config binding changed")
    return {
        "role": role,
        "stage": "dpo",
        "adapter_path": str(adapter),
        "adapter_sha256": manifest["adapter_sha256"],
        "training_manifest_sha256": sha256_file(manifest_path),
    }


def performance_tuple(metrics: dict[str, int]) -> tuple[int, ...]:
    return tuple(metrics[key] for key in PERFORMANCE_KEYS)


def select_variant(metrics_by_role: dict[str, dict[str, int]]) -> dict[str, Any]:
    require(set(metrics_by_role) == set(ROLES), "A5 dev selection roles changed")
    baseline = metrics_by_role["baseline"]
    candidates = {role: metrics_by_role[role] for role in ("beta01", "beta03")}
    eligibility = {
        role: (
            metrics["timeouts"] <= baseline["timeouts"]
            and metrics["regression_failures"] <= baseline["regression_failures"]
        )
        for role, metrics in candidates.items()
    }
    positive = {
        role: performance_tuple(metrics) > performance_tuple(baseline)
        for role, metrics in candidates.items()
    }
    promotable = [role for role in candidates if eligibility[role] and positive[role]]
    tie = {"beta01": 0, "beta03": 1}
    if promotable:
        selected = max(promotable, key=lambda role: (performance_tuple(candidates[role]), tie[role]))
        reason = "eligible_positive_execution_signal"
    else:
        selected = min(
            candidates,
            key=lambda role: (
                candidates[role]["regression_failures"],
                candidates[role]["timeouts"],
                tuple(-value for value in performance_tuple(candidates[role])),
                0 if role == "beta03" else 1,
            ),
        )
        reason = "lower_risk_negative_or_no_improvement"
    return {
        "selected": selected,
        "reason": reason,
        "baseline": baseline,
        "candidates": candidates,
        "eligible": eligibility,
        "positive_signal": positive,
        "selected_is_promotable": eligibility[selected] and positive[selected],
    }
