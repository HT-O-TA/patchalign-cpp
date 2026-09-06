"""Run the frozen six-part A3 generalization-failure diagnosis.

The analysis is deliberately read-only.  It verifies every frozen input hash,
emits aggregates and case identifiers only, and never copies source, tests, or
model patches into the output directory.
"""

from __future__ import annotations

import argparse
from collections import Counter
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterable


VERSION = "a3-generalization-diagnostic-v1"
FUNCTION_PATTERN = re.compile(
    r"(?m)^[^#\n;{}]*?\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?\{"
)
CONTROL_NAMES = {"if", "for", "while", "switch", "catch"}
INTERNAL_TERMINAL_RANK = {
    "parse_failed": 0,
    "policy_violation": 1,
    "apply_failed": 2,
    "build_failed": 3,
    "public_test_failed": 4,
    "hidden_test_failed": 5,
    "regression_failed": 6,
    "sanitizer_failed": 7,
    "success": 8,
}
EXTERNAL_TERMINAL_RANK = {
    "parse_failed": 0,
    "policy_violation": 1,
    "apply_failed": 2,
    "build_failed": 3,
    "test_failed": 4,
    "success": 5,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def resolve(repo: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def verify_input(repo: Path, spec: dict[str, Any], key: str) -> Path:
    path = resolve(repo, spec[key])
    expected = spec[f"{key}_sha256"]
    if not path.is_file():
        raise RuntimeError(f"missing frozen input: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {key}: expected {expected}, got {actual}")
    return path


def indexed(rows: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row[key])
        if value in result:
            raise RuntimeError(f"duplicate {key}: {value}")
        result[value] = row
    return result


def require_same_ids(label: str, expected: set[str], actual: set[str]) -> None:
    if expected != actual:
        raise RuntimeError(
            f"{label} ID mismatch: missing={len(expected-actual)}, extra={len(actual-expected)}"
        )


def function_names(code: str) -> set[str]:
    return {match.group(1) for match in FUNCTION_PATTERN.finditer(code)} - CONTROL_NAMES


def classify_edit(old: str, new: str, changed: int) -> str:
    """Exact edit classifier frozen by build_a3_formal_sft_data.py."""
    for name in function_names(new) - function_names(old):
        if len(re.findall(rf"\b{re.escape(name)}\s*\(", new)) >= 2:
            return "add_helper"
    if changed == 1:
        return "single_line"
    if changed <= 20:
        return "multi_line_local"
    return "localized_refactor"


def diff_changed_lines(old: str, new: str, filename: str) -> int:
    """Exact max(additions, deletions) convention used by A1/A2/A3."""
    patch = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="\n",
        )
    )
    additions = deletions = 0
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return max(additions, deletions)


def bin_label(value: float, boundaries: list[int]) -> str:
    for left, right in zip(boundaries, boundaries[1:]):
        if left <= value < right:
            return f"[{left},{right})"
    raise RuntimeError(f"value {value} outside configured bins {boundaries}")


def numeric_summary(values: Iterable[float]) -> dict[str, float | int]:
    data = sorted(float(value) for value in values)
    if not data:
        return {"count": 0}

    def percentile(q: float) -> float:
        index = (len(data) - 1) * q
        lower, upper = math.floor(index), math.ceil(index)
        if lower == upper:
            return data[lower]
        return data[lower] * (upper - index) + data[upper] * (index - lower)

    return {
        "count": len(data),
        "min": data[0],
        "p25": percentile(0.25),
        "median": percentile(0.5),
        "p75": percentile(0.75),
        "max": data[-1],
        "mean": sum(data) / len(data),
    }


def ks_distance(left: Iterable[float], right: Iterable[float]) -> float:
    a, b = sorted(left), sorted(right)
    points = sorted(set(a) | set(b))
    if not a or not b:
        raise RuntimeError("KS distance requires two non-empty samples")
    return max(
        abs(sum(x <= point for x in a) / len(a) - sum(x <= point for x in b) / len(b))
        for point in points
    )


def categorical_summary(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def total_variation(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        raise RuntimeError("total variation requires two non-empty samples")
    labels = set(left) | set(right)
    return 0.5 * sum(
        abs(left[label] / left.total() - right[label] / right.total()) for label in labels
    )


def partition_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, list):
            result[str(key)] = len(item)
        elif isinstance(item, int):
            result[str(key)] = item
    return result


def internal_features(
    root: Path,
    cases: list[dict[str, Any]],
    prompts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for case in cases:
        case_id = case["case_id"]
        old = (root / "cases" / case_id / "buggy.cpp").read_text(encoding="utf-8")
        new = (root / "cases" / case_id / "fixed.cpp").read_text(encoding="utf-8")
        changed = int(case["changed_logical_lines"])
        measured = diff_changed_lines(old, new, "main.cpp")
        if measured != changed:
            raise RuntimeError(f"changed-line drift for {case_id}: {changed} != {measured}")
        prompt = prompts[case_id]
        partitions = partition_counts(case.get("test_partition"))
        result.append(
            {
                "case_id": case_id,
                "problem_id": str(case["problem_id"]),
                "source_shard": str(case["source_shard"]),
                "upstream_split": str(case["upstream_split"]),
                "task_level": str(case["task_level"]),
                "edit_type": classify_edit(old, new, changed),
                "changed_logical_lines": changed,
                "code_lines": len(old.splitlines()),
                "test_count": int(case["test_count"]),
                "test_partition_counts": partitions,
                "prompt_tokens": int(prompt["rendered_input_tokens"]),
                "prompt_version": str(prompt["prompt_version"]),
            }
        )
    return result


def distribution_shift(
    formal: list[dict[str, Any]],
    confirmation: list[dict[str, Any]],
    bins: dict[str, list[int]],
) -> dict[str, Any]:
    categorical = ["source_shard", "upstream_split", "task_level", "edit_type", "prompt_version"]
    numeric = ["code_lines", "changed_logical_lines", "test_count", "prompt_tokens"]
    result: dict[str, Any] = {
        "problem_family_overlap": len(
            {row["problem_id"] for row in formal} & {row["problem_id"] for row in confirmation}
        ),
        "categorical": {},
        "numeric": {},
        "test_partitions": {},
    }
    for key in categorical:
        left, right = Counter(row[key] for row in formal), Counter(row[key] for row in confirmation)
        result["categorical"][key] = {
            "formal": dict(sorted(left.items())),
            "confirmation": dict(sorted(right.items())),
            "total_variation": total_variation(left, right),
        }
    for key in numeric:
        left = [row[key] for row in formal]
        right = [row[key] for row in confirmation]
        item: dict[str, Any] = {
            "formal": numeric_summary(left),
            "confirmation": numeric_summary(right),
            "ks_distance": ks_distance(left, right),
        }
        configured = bins.get(key.replace("changed_logical_lines", "changed_lines"))
        if configured:
            item["formal_bins"] = categorical_summary(bin_label(x, configured) for x in left)
            item["confirmation_bins"] = categorical_summary(bin_label(x, configured) for x in right)
        result["numeric"][key] = item
    labels = sorted(
        {label for row in formal + confirmation for label in row["test_partition_counts"]}
    )
    for label in labels:
        result["test_partitions"][label] = {
            "formal": numeric_summary(row["test_partition_counts"].get(label, 0) for row in formal),
            "confirmation": numeric_summary(
                row["test_partition_counts"].get(label, 0) for row in confirmation
            ),
        }
    return result


def terminal_summary(rows: list[dict[str, Any]], external: bool = False) -> dict[str, Any]:
    ranks = EXTERNAL_TERMINAL_RANK if external else INTERNAL_TERMINAL_RANK
    terminals = Counter(str(row["terminal_classification"]) for row in rows)
    unknown = set(terminals) - set(ranks)
    if unknown:
        raise RuntimeError(f"unknown terminal classifications: {sorted(unknown)}")
    if external:
        thresholds = {"parse": 1, "policy": 2, "apply": 3, "build": 4, "tests": 5}
    else:
        thresholds = {
            "parse": 1,
            "policy": 2,
            "apply": 3,
            "build": 4,
            "public": 5,
            "hidden": 6,
            "regression": 8,
        }
    funnel = {
        stage: sum(ranks[str(row["terminal_classification"])] >= threshold for row in rows)
        for stage, threshold in thresholds.items()
    }
    return {
        "count": len(rows),
        "terminal_classifications": dict(sorted(terminals.items())),
        "funnel_counts": funnel,
        "funnel_rates": {key: value / len(rows) for key, value in funnel.items()},
    }


def compact_stage(stage: Any) -> dict[str, Any]:
    if not isinstance(stage, dict):
        return {"status": "not_run"}
    result = {key: stage[key] for key in ("status", "matched", "total", "timed_out") if key in stage}
    outcomes = stage.get("outcomes")
    if isinstance(outcomes, list):
        result["outcome_statuses"] = dict(
            sorted(Counter(str(item.get("status", "unknown")) for item in outcomes).items())
        )
        result["timeout_count"] = sum(bool(item.get("timed_out")) for item in outcomes)
    return result


def exact_internal_fix(case_root: Path, case_id: str, patch: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="patchalign-generalization-") as temp:
        work = Path(temp)
        shutil.copyfile(case_root / "cases" / case_id / "buggy.cpp", work / "main.cpp")
        completed = subprocess.run(
            ["git", "apply", "--recount", "-"],
            cwd=work,
            input=patch,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            return False
        actual = (work / "main.cpp").read_text(encoding="utf-8")
        expected = (case_root / "cases" / case_id / "fixed.cpp").read_text(encoding="utf-8")
        return actual == expected


def confirmation_audit(
    features: dict[str, dict[str, Any]],
    scores: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    case_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    regression_rows = [row for row in scores if row["terminal_classification"] == "regression_failed"]
    timeout_rows: list[tuple[dict[str, Any], list[str], int]] = []
    for row in scores:
        stages = row.get("stages", {})
        timeout_stages: list[str] = []
        timeout_count = 0
        for stage_name in ("public", "hidden", "regression"):
            outcomes = stages.get(stage_name, {}).get("outcomes", [])
            count = sum(bool(item.get("timed_out")) for item in outcomes)
            if count:
                timeout_stages.append(stage_name)
                timeout_count += count
        if timeout_stages:
            timeout_rows.append((row, timeout_stages, timeout_count))

    regression_ids = {row["case_id"] for row in regression_rows}
    timeout_map = {row["case_id"]: (stages, count) for row, stages, count in timeout_rows}
    for case_id in sorted(regression_ids | set(timeout_map)):
        score = next(row for row in scores if row["case_id"] == case_id)
        feature = features[case_id]
        prediction = predictions[case_id]
        timeout_stages, timeout_count = timeout_map.get(case_id, ([], 0))
        audits.append(
            {
                "case_id": case_id,
                "audit_kinds": sorted(
                    (["regression"] if case_id in regression_ids else [])
                    + (["timeout"] if case_id in timeout_map else [])
                ),
                "problem_id": feature["problem_id"],
                "task_level": feature["task_level"],
                "edit_type": feature["edit_type"],
                "code_lines": feature["code_lines"],
                "changed_logical_lines": feature["changed_logical_lines"],
                "test_count": feature["test_count"],
                "terminal_classification": score["terminal_classification"],
                "timeout_stages": timeout_stages,
                "timeout_outcome_count": timeout_count,
                "stage_summary": {
                    key: compact_stage(value) for key, value in score.get("stages", {}).items()
                },
                "exact_reference_fix": exact_internal_fix(
                    case_root, case_id, str(prediction.get("extracted_patch", ""))
                ),
            }
        )
    return audits, {
        "regression_case_count": len(regression_rows),
        "regression_case_ids": sorted(regression_ids),
        "timeout_case_count": len(timeout_rows),
        "timeout_case_ids": sorted(timeout_map),
        "timeout_outcome_count": sum(item[2] for item in timeout_rows),
    }


def group_success(
    features: list[dict[str, Any]],
    success_ids: set[str],
    key: str,
) -> dict[str, Any]:
    totals = Counter(str(row[key]) for row in features)
    successes = Counter(str(row[key]) for row in features if row["case_id"] in success_ids)
    return {
        label: {
            "total": totals[label],
            "success": successes[label],
            "success_rate": successes[label] / totals[label],
            "share_of_successes": successes[label] / len(success_ids),
        }
        for label in sorted(totals)
    }


def formal_success_concentration(
    features: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    case_root: Path,
    bins: dict[str, list[int]],
) -> dict[str, Any]:
    success_ids = {row["case_id"] for row in scores if row["success"]}
    enriched = []
    for row in features:
        copy = dict(row)
        copy["code_line_bin"] = bin_label(row["code_lines"], bins["code_lines"])
        copy["prompt_token_bin"] = bin_label(row["prompt_tokens"], bins["prompt_tokens"])
        copy["test_count_bin"] = bin_label(row["test_count"], bins["test_count"])
        enriched.append(copy)
    dimensions = [
        "task_level",
        "edit_type",
        "source_shard",
        "upstream_split",
        "code_line_bin",
        "prompt_token_bin",
        "test_count_bin",
        "prompt_version",
    ]
    exact = [
        case_id
        for case_id in sorted(success_ids)
        if exact_internal_fix(
            case_root, case_id, str(predictions[case_id].get("extracted_patch", ""))
        )
    ]
    return {
        "success_count": len(success_ids),
        "success_case_ids": sorted(success_ids),
        "exact_reference_fix_count": len(exact),
        "exact_reference_fix_case_ids": exact,
        "groups": {key: group_success(enriched, success_ids, key) for key in dimensions},
    }


def percentile_rank(values: list[int], target: int) -> float:
    return sum(value <= target for value in values) / len(values)


def external_representativeness(
    cases: list[dict[str, Any]],
    scores: list[dict[str, Any]],
) -> dict[str, Any]:
    success_rows = [row for row in scores if row["success"]]
    by_id = indexed(cases, "case_id")
    projects = Counter(str(case["project"]) for case in cases)
    tokens = [int(case["input_tokens"]) for case in cases]
    details = []
    for score in success_rows:
        case = by_id[score["case_id"]]
        project = str(case["project"])
        project_scores = [row for row in scores if str(row["project"]) == project]
        details.append(
            {
                "case_id": case["case_id"],
                "project": project,
                "source_file": case["source_file"],
                "input_tokens": int(case["input_tokens"]),
                "input_token_percentile_rank": percentile_rank(tokens, int(case["input_tokens"])),
                "project_case_count": projects[project],
                "project_dataset_share": projects[project] / len(cases),
                "project_success_count": sum(bool(row["success"]) for row in project_scores),
                "project_success_rate": sum(bool(row["success"]) for row in project_scores)
                / len(project_scores),
            }
        )
    return {
        "dataset_case_count": len(cases),
        "project_count": len(projects),
        "project_distribution": dict(sorted(projects.items())),
        "input_tokens": numeric_summary(tokens),
        "success_count": len(success_rows),
        "successes": details,
        "cross_project_success_count": len({item["project"] for item in details}),
    }


def synthesis(
    formal_m0: dict[str, Any],
    formal_r2: dict[str, Any],
    confirm_m0: dict[str, Any],
    confirm_r2: dict[str, Any],
    external_m0: dict[str, Any],
    external_r2: dict[str, Any],
    shift: dict[str, Any],
    a4: dict[str, Any],
) -> dict[str, Any]:
    same_template = shift["categorical"]["prompt_version"]["total_variation"] == 0
    confirm_pass = confirm_r2["terminal_classifications"].get("success", 0)
    external_pass_delta = (
        external_r2["terminal_classifications"].get("success", 0)
        - external_m0["terminal_classifications"].get("success", 0)
    )
    protocol_gain = (
        formal_r2["funnel_rates"]["parse"] > formal_m0["funnel_rates"]["parse"]
        and confirm_r2["funnel_rates"]["parse"] > confirm_m0["funnel_rates"]["parse"]
        and external_r2["funnel_rates"]["parse"] > external_m0["funnel_rates"]["parse"]
    )
    return {
        "primary_verdict": "protocol_learning_without_demonstrated_semantic_generalization",
        "protocol_learning_supported": protocol_gain,
        "pure_prompt_template_shift_ruled_out": same_template and confirm_pass == 0,
        "cross_dataset_end_to_end_gain": external_pass_delta,
        "confirmation_success_count": confirm_pass,
        "formal_success_count": formal_r2["terminal_classifications"].get("success", 0),
        "a4_train_only_sampled_success_rate": a4["execution"]["all"]["rates"]["success"],
        "a4_comparability_warning": (
            "A4 uses train-only sampled candidates and is not a like-for-like unseen greedy evaluation."
        ),
        "causal_limit": (
            "The frozen observational evidence separates output-protocol learning from end-to-end "
            "repair success, but cannot identify one exclusive cause for semantic failure."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["version"] != VERSION or len(config["checks"]) != 6:
        raise RuntimeError("unsupported diagnostic contract")

    loaded: dict[str, dict[str, Any]] = {}
    input_hashes: dict[str, str] = {str(config_path): sha256_file(config_path)}
    for name in ("internal", "confirmation", "external"):
        spec = config[name]
        paths = {}
        for key in ("manifest", "prompts", "m0_scores", "r2_predictions", "r2_scores"):
            path = verify_input(repo, spec, key)
            paths[key] = path
            input_hashes[str(path)] = sha256_file(path)
        manifest_obj = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        cases = manifest_obj["cases"]
        prompts = indexed(read_jsonl(paths["prompts"]), "case_id")
        m0_scores = read_jsonl(paths["m0_scores"])
        r2_scores = read_jsonl(paths["r2_scores"])
        predictions = indexed(read_jsonl(paths["r2_predictions"]), "sample_id")
        case_ids = {str(case["case_id"]) for case in cases}
        if len(cases) != spec["expected_cases"]:
            raise RuntimeError(f"{name} expected {spec['expected_cases']} cases, got {len(cases)}")
        require_same_ids(f"{name} prompts", case_ids, set(prompts))
        require_same_ids(f"{name} M0 scores", case_ids, {row["case_id"] for row in m0_scores})
        require_same_ids(f"{name} R2 scores", case_ids, {row["case_id"] for row in r2_scores})
        require_same_ids(f"{name} R2 predictions", case_ids, set(predictions))
        loaded[name] = {
            "spec": spec,
            "cases": cases,
            "prompts": prompts,
            "m0_scores": m0_scores,
            "r2_scores": r2_scores,
            "predictions": predictions,
        }
        print(f"loaded {name}: {len(cases)} cases", flush=True)

    a4_path = verify_input(repo, config["a4"], "summary")
    input_hashes[str(a4_path)] = sha256_file(a4_path)
    a4 = json.loads(a4_path.read_text(encoding="utf-8"))
    formal_root = Path(config["internal"]["case_root"])
    confirm_root = Path(config["confirmation"]["case_root"])
    formal_features = internal_features(
        formal_root, loaded["internal"]["cases"], loaded["internal"]["prompts"]
    )
    print(f"formal features complete: {len(formal_features)}", flush=True)
    confirm_features = internal_features(
        confirm_root, loaded["confirmation"]["cases"], loaded["confirmation"]["prompts"]
    )
    print(f"confirmation features complete: {len(confirm_features)}", flush=True)
    shift = distribution_shift(formal_features, confirm_features, config["bins"])
    formal_m0 = terminal_summary(loaded["internal"]["m0_scores"])
    formal_r2 = terminal_summary(loaded["internal"]["r2_scores"])
    confirm_m0 = terminal_summary(loaded["confirmation"]["m0_scores"])
    confirm_r2 = terminal_summary(loaded["confirmation"]["r2_scores"])
    external_m0 = terminal_summary(loaded["external"]["m0_scores"], external=True)
    external_r2 = terminal_summary(loaded["external"]["r2_scores"], external=True)
    print("distribution and funnels complete", flush=True)
    audits, audit_summary = confirmation_audit(
        indexed(confirm_features, "case_id"),
        loaded["confirmation"]["r2_scores"],
        loaded["confirmation"]["predictions"],
        confirm_root,
    )
    print(f"confirmation audit complete: {len(audits)} cases", flush=True)
    concentration = formal_success_concentration(
        formal_features,
        loaded["internal"]["r2_scores"],
        loaded["internal"]["predictions"],
        formal_root,
        config["bins"],
    )
    print("formal success concentration complete", flush=True)
    representativeness = external_representativeness(
        loaded["external"]["cases"], loaded["external"]["r2_scores"]
    )
    print("external representativeness complete", flush=True)
    if concentration["success_count"] != config["internal"]["expected_r2_successes"]:
        raise RuntimeError("formal success-count drift")
    if audit_summary["regression_case_count"] != config["confirmation"]["expected_regressions"]:
        raise RuntimeError("confirmation regression-count drift")
    if audit_summary["timeout_case_count"] != config["confirmation"]["expected_timeouts"]:
        raise RuntimeError("confirmation timeout-count drift")
    if representativeness["success_count"] != config["external"]["expected_r2_successes"]:
        raise RuntimeError("external success-count drift")

    summary = {
        "version": VERSION,
        "checks_completed": list(config["checks"]),
        "check_1_distribution_shift": shift,
        "check_2_confirmation_terminal_funnel": {"m0": confirm_m0, "m1_r2": confirm_r2},
        "check_3_confirmation_failure_audit": audit_summary,
        "check_4_formal_success_concentration": concentration,
        "check_5_external_success_representativeness": representativeness,
        "check_6_protocol_style_vs_repair_semantics": synthesis(
            formal_m0,
            formal_r2,
            confirm_m0,
            confirm_r2,
            external_m0,
            external_r2,
            shift,
            a4,
        ),
        "supporting_funnels": {
            "formal": {"m0": formal_m0, "m1_r2": formal_r2},
            "external": {"m0": external_m0, "m1_r2": external_r2},
        },
    }

    output = (args.output_dir or resolve(repo, config["output_dir"])).resolve()
    if output.exists() and any(output.iterdir()) and not args.force:
        raise RuntimeError(f"refusing to overwrite non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / "summary.json"
    audit_path = output / "case-audit.jsonl"
    write_json(summary_path, summary)
    audit_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in audits),
        encoding="utf-8",
    )
    output_hashes = {
        "summary.json": sha256_file(summary_path),
        "case-audit.jsonl": sha256_file(audit_path),
    }
    run_manifest = {
        "version": VERSION,
        "config_sha256": sha256_file(config_path),
        "input_hashes": dict(sorted(input_hashes.items())),
        "output_hashes": output_hashes,
        "privacy": "Aggregates, IDs and hashes only; no source, test text, or model patch copied.",
        "mutations": "None outside the designated output directory.",
    }
    write_json(output / "run-manifest.json", run_manifest)
    print(json.dumps({"output_dir": str(output), **output_hashes}, sort_keys=True))


if __name__ == "__main__":
    main()
