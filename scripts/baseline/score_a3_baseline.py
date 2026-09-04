"""Score A3.0 model predictions with the verified A2 Bubblewrap boundary."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
from typing import Any

from jsonschema import Draft202012Validator

from patchalign.evaluation.patches import (
    PatchParseError,
    PatchPolicyError,
    enforce_patch_policy,
    normalize_terminal_lf,
    parse_unified_diff,
)
from scripts.data.a2_output_matcher import matcher_metadata, outputs_match
from scripts.data.a2_sandbox_runtime import (
    SANDBOX_VERSION,
    public_result,
    resolve_bwrap,
    run_sandboxed,
)


STAGES = ("parse", "policy", "apply", "build", "public", "hidden", "regression")

STRICT_SCORING_PROTOCOL = "a3-scoring-v1-strict-raw"
A31_SCORING_PROTOCOL = "a3-scoring-v2"
A31_TERMINAL_LF_RULE = "append_one_lf_if_nonempty_and_missing"


def load_scoring_protocol(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "input_field",
        "transport_normalization",
        "parser",
        "allowed_paths",
        "apply_command",
        "forbidden_transforms",
    }
    if set(config) != required:
        raise ValueError("A3.1 scoring config fields differ from the frozen contract")
    if (
        config["version"] != A31_SCORING_PROTOCOL
        or config["input_field"] != "raw_text"
        or config["transport_normalization"]
        != {
            "rule": A31_TERMINAL_LF_RULE,
            "maximum_added_bytes": 1,
        }
        or config["parser"] != "strict_unified_diff"
        or config["allowed_paths"] != ["main.cpp"]
        or config["apply_command"] != ["git", "apply", "--recount"]
        or config["forbidden_transforms"]
        != [
            "strip_markdown_fences",
            "strip_explanations",
            "trim_whitespace",
            "rewrite_hunk_headers",
            "rewrite_paths",
            "recover_partial_diff",
        ]
    ):
        raise ValueError("A3.1 scoring config does not match the frozen semantics")
    return config


def prepare_patch_text(raw_text: str, scoring_protocol: str) -> tuple[str, bool]:
    if scoring_protocol == STRICT_SCORING_PROTOCOL:
        return raw_text, False
    if scoring_protocol == A31_SCORING_PROTOCOL:
        return normalize_terminal_lf(raw_text)
    raise ValueError(f"unsupported scoring protocol: {scoring_protocol}")



def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def not_run_stages() -> dict[str, dict[str, Any]]:
    return {name: {"status": "not_run"} for name in STAGES}


def normalized_command(result: dict[str, Any]) -> dict[str, Any]:
    status = {"pass": "passed", "fail": "failed", "timeout": "failed"}[result["status"]]
    normalized = public_result(result)
    return {**normalized, "status": status}


def load_predictions(path: Path, schema_path: Path) -> list[dict[str, Any]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    records = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        validator.validate(record)
        sample_id = record["sample_id"]
        if sample_id in seen:
            raise RuntimeError(f"duplicate prediction: {sample_id}")
        seen.add(sample_id)
        records.append(record)
    return records


def run_suite(
    executable: Path,
    test_ids: list[Any],
    tests: dict[str, dict[str, Any]],
    problem_id: str,
    bwrap: Path,
) -> dict[str, Any]:
    outcomes = []
    for test_id in test_ids:
        test = tests[str(test_id)]
        with tempfile.TemporaryDirectory(prefix="patchalign-a30-test-") as directory:
            workspace = Path(directory)
            shutil.copyfile(executable, workspace / "main")
            (workspace / "main").chmod(0o500)
            result = run_sandboxed(
                workspace,
                ["/work/main"],
                bwrap,
                input_text=test["input"],
                timeout=60,
            )
        matched = result["status"] == "pass" and outputs_match(
            test["output"], result["stdout"], problem_id
        )
        outcome = {
            "test_id": test_id,
            "matched": matched,
            **public_result(result),
        }
        if result["status"] != "pass":
            outcome["error_tail"] = result["stderr"][-1000:]
        outcomes.append(outcome)
    passed = bool(outcomes) and all(item["matched"] for item in outcomes)
    return {
        "status": "passed" if passed else "failed",
        "total": len(outcomes),
        "matched": sum(item["matched"] for item in outcomes),
        "outcomes": outcomes,
    }


def score_prediction(
    item: dict[str, Any],
    case_dir: Path,
    prediction: dict[str, Any],
    bwrap: Path,
    *, scoring_protocol: str = STRICT_SCORING_PROTOCOL,
) -> dict[str, Any]:
    stages = not_run_stages()
    raw_text = prediction.get("raw_text", "")
    evaluated_text, terminal_lf_added = prepare_patch_text(raw_text, scoring_protocol)
    record: dict[str, Any] = {
        "schema_version": "a3-score-v0.1",
        "case_id": item["case_id"],
        "problem_id": item["problem_id"],
        "task_level": item["task_level"],
        "prediction_sha256": sha256_bytes(raw_text.encode("utf-8")),
        "sandbox": {
            "backend": "bubblewrap",
            "policy_version": SANDBOX_VERSION,
        },
        "output_matcher": matcher_metadata(),
        "stages": stages,
    }

    if scoring_protocol == A31_SCORING_PROTOCOL:
        record.update(
            schema_version="a3-score-v0.2",
            scoring_protocol_version=scoring_protocol,
            evaluated_patch_sha256=sha256_bytes(evaluated_text.encode("utf-8")),
            transport_normalization={
                "rule": A31_TERMINAL_LF_RULE,
                "terminal_lf_added": terminal_lf_added,
                "added_bytes": int(terminal_lf_added),
            },
        )

    if prediction["sample_id"] != item["case_id"]:
        stages["parse"] = {"status": "failed", "reason": "sample_id_mismatch"}
        record.update(terminal_classification="parse_failed", success=False)
        return record
    if prediction["status"] != "ok":
        record.update(terminal_classification="generation_failed", success=False)
        return record

    try:
        parsed = parse_unified_diff(evaluated_text)
    except PatchParseError as exc:
        stages["parse"] = {"status": "failed", "reason": str(exc)}
        record.update(terminal_classification="parse_failed", success=False)
        return record
    stages["parse"] = {"status": "passed", "file_count": len(parsed.files)}
    try:
        changed = enforce_patch_policy(parsed, ["main.cpp"])
    except PatchPolicyError as exc:
        stages["policy"] = {"status": "failed", "reason": str(exc)}
        record.update(terminal_classification="policy_violation", success=False)
        return record
    stages["policy"] = {"status": "passed", "changed_paths": list(changed)}

    tests = {
        str(test["id"]): test
        for test in map(
            json.loads, (case_dir / "tests.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    partitions = json.loads(
        (case_dir / "test-partition.json").read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="patchalign-a30-score-") as directory:
        workspace = Path(directory)
        shutil.copyfile(case_dir / "buggy.cpp", workspace / "main.cpp")
        check = run_sandboxed(
            workspace,
            ["/usr/bin/git", "apply", "--recount", "--check", "-"],
            bwrap,
            input_text=evaluated_text,
            timeout=30,
        )
        if check["status"] != "pass":
            stages["apply"] = {
                **normalized_command(check),
                "reason": "git_apply_check_failed",
                "error_tail": check["stderr"][-2000:],
            }
            record.update(terminal_classification="apply_failed", success=False)
            return record
        applied = run_sandboxed(
            workspace,
            ["/usr/bin/git", "apply", "--recount", "-"],
            bwrap,
            input_text=evaluated_text,
            timeout=30,
        )
        stages["apply"] = normalized_command(applied)
        if applied["status"] != "pass":
            record.update(terminal_classification="apply_failed", success=False)
            return record

        compiled = run_sandboxed(
            workspace,
            ["/usr/bin/g++", "-std=c++17", "-O2", "main.cpp", "-o", "main"],
            bwrap,
            timeout=120,
        )
        stages["build"] = normalized_command(compiled)
        if compiled["status"] != "pass":
            stages["build"]["error_tail"] = compiled["stderr"][-2000:]
            record.update(terminal_classification="build_failed", success=False)
            return record
        executable = workspace / "main"
        if not executable.is_file() or executable.is_symlink():
            stages["build"] = {
                "status": "failed",
                "reason": "compiler_did_not_create_regular_executable",
            }
            record.update(terminal_classification="build_failed", success=False)
            return record

        for suite, classification in (
            ("public", "public_test_failed"),
            ("hidden", "hidden_test_failed"),
            ("regression", "regression_failed"),
        ):
            stages[suite] = run_suite(
                executable,
                partitions[suite],
                tests,
                str(item["problem_id"]),
                bwrap,
            )
            if stages[suite]["status"] != "passed":
                record.update(terminal_classification=classification, success=False)
                return record

    record.update(terminal_classification="success", success=True)
    return record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:

    protocols = {
        record.get("scoring_protocol_version", STRICT_SCORING_PROTOCOL)
        for record in records
    }
    if len(protocols) != 1:
        raise ValueError("cannot summarize mixed scoring protocols")
    scoring_protocol = next(iter(protocols))

    def one_slice(selected: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(selected)
        classifications = Counter(
            record["terminal_classification"] for record in selected
        )
        counts = {
            "total": total,
            "parse_success": sum(
                record["stages"]["parse"]["status"] == "passed" for record in selected
            ),
            "apply_success": sum(
                record["stages"]["apply"]["status"] == "passed" for record in selected
            ),
            "compile_success": sum(
                record["stages"]["build"]["status"] == "passed" for record in selected
            ),
            "public_test_success": sum(
                record["stages"]["public"]["status"] == "passed" for record in selected
            ),
            "hidden_test_pass_at_1": sum(record["success"] for record in selected),
            "regression_failures": classifications["regression_failed"],
            "format_violations": (
                classifications["parse_failed"] + classifications["policy_violation"]
            ),
            "timeouts": sum(
                any(
                    stage.get("timed_out", False)
                    or any(x.get("timed_out", False) for x in stage.get("outcomes", []))
                    for stage in record["stages"].values()
                )
                for record in selected
            ),
            "success": sum(record["success"] for record in selected),
        }
        rates = {
            key: value / total if total else 0.0
            for key, value in counts.items()
            if key != "total"
        }
        return {
            "counts": counts,
            "rates": rates,
            "terminal_classifications": dict(sorted(classifications.items())),
        }

    summary = {
        "version": (
            "a3-baseline-score-v2"
            if scoring_protocol == A31_SCORING_PROTOCOL
            else "a3-baseline-score-v1"
        ),
        "all": one_slice(records),
        "function": one_slice(
            [record for record in records if record["task_level"] == "function"]
        ),
        "file_window": one_slice(
            [record for record in records if record["task_level"] == "file_window"]
        ),
        "sandbox": {
            "backend": "bubblewrap",
            "policy_version": SANDBOX_VERSION,
        },
        "output_matcher": matcher_metadata(),
    }

    if scoring_protocol == A31_SCORING_PROTOCOL:
        summary.update(
            scoring_protocol_version=scoring_protocol,
            transport_normalization={
                "rule": A31_TERMINAL_LF_RULE,
                "terminal_lf_added": sum(
                    record["transport_normalization"]["terminal_lf_added"]
                    for record in records
                ),
                "raw_prediction_hash_preserved": True,
            },
        )

    summary["summary_sha256"] = sha256_bytes(
        json.dumps(
            summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    return summary


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--inference-manifest", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scoring-config", type=Path)
    parser.add_argument("--manifest-name", default="a2-manifest.json")
    args = parser.parse_args()

    bwrap = resolve_bwrap(args.bwrap)
    if args.output_dir.exists():
        raise SystemExit(f"refusing to overwrite output directory: {args.output_dir}")
    repo = Path(__file__).resolve().parents[2]

    if args.scoring_config is None:
        scoring_protocol = STRICT_SCORING_PROTOCOL
        scoring_config_sha256 = None
    else:
        load_scoring_protocol(args.scoring_config)
        scoring_protocol = A31_SCORING_PROTOCOL
        scoring_config_sha256 = sha256_file(args.scoring_config)

    predictions = load_predictions(
        args.predictions, repo / "schemas" / "prediction-v0.1.schema.json"
    )
    manifest_path = args.holdout_dir / args.manifest_name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_ids = [item["case_id"] for item in manifest["cases"]]
    actual_ids = [record["sample_id"] for record in predictions]
    if actual_ids != expected_ids:
        raise SystemExit("prediction order or frozen denominator differs from dataset manifest")
    inference_manifest = json.loads(
        args.inference_manifest.read_text(encoding="utf-8")
    )
    current_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo, text=True
        ).strip()
    )
    if dirty:
        raise SystemExit("scorer worktree is dirty")
    if (
        scoring_protocol == STRICT_SCORING_PROTOCOL
        and current_commit != inference_manifest["git_commit"]
    ):
        raise SystemExit("strict-v1 scorer worktree does not match inference git commit")
    if inference_manifest["prediction_artifact_sha256"] != sha256_file(
        args.predictions
    ):
        raise SystemExit("prediction artifact hash does not match inference manifest")
    if inference_manifest["dataset_manifest_sha256"] != sha256_file(
        manifest_path
    ):
        raise SystemExit("dataset manifest hash mismatch")

    args.output_dir.mkdir(parents=True)
    results = []
    score_started_at = utc_now()
    by_prediction = {record["sample_id"]: record for record in predictions}
    for index, item in enumerate(manifest["cases"], start=1):
        case_dir = args.holdout_dir / "cases" / item["case_id"]
        result = score_prediction(
            item,
            case_dir,
            by_prediction[item["case_id"]],
            bwrap,
            scoring_protocol=scoring_protocol,
        )
        results.append(result)
        print(
            json.dumps(
                {
                    "case": item["case_id"],
                    "classification": result["terminal_classification"],
                    "index": index,
                    "success": result["success"],
                    "total": len(manifest["cases"]),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    scores_path = args.output_dir / "scores.jsonl"
    scores_path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in results
        )
        + "\n",
        encoding="utf-8",
    )
    summary = summarize(results)
    write_json(args.output_dir / "score-summary.json", summary)
    is_a31 = scoring_protocol == A31_SCORING_PROTOCOL
    score_job_id = os.environ.get("SLURM_JOB_ID")
    a31_suffix = f"_score_a31_{score_job_id}" if score_job_id else "_score_a31"
    summary_artifact_sha256 = sha256_file(args.output_dir / "score-summary.json")
    score_manifest = {
        "schema_version": "0.2.0" if is_a31 else "0.1.0",
        "run_id": inference_manifest["run_id"] + (
            a31_suffix if is_a31 else "_score"
        ),
        "stage": "evaluation",
        "started_at": score_started_at,
        "finished_at": utc_now(),
        "git_commit": current_commit if is_a31 else inference_manifest["git_commit"],
        "dirty_worktree": False,
        "config_sha256": (
            scoring_config_sha256 if is_a31 else inference_manifest["config_sha256"]
        ),
        "model_id": inference_manifest["model_id"],
        "model_revision": inference_manifest["model_revision"],
        "model_config_sha256": inference_manifest["model_config_sha256"],
        "adapter_sha256": inference_manifest.get("adapter_sha256"),
        "dataset_manifest_sha256": inference_manifest["dataset_manifest_sha256"],
        "environment_sha256": inference_manifest["environment_sha256"],
        "seed": inference_manifest["seed"],
        "slurm_job_id": score_job_id,
        "prediction_artifact_sha256": inference_manifest[
            "prediction_artifact_sha256"
        ],
        "execution_artifact_sha256": sha256_file(scores_path),
        "notes": f"summary_sha256={summary_artifact_sha256}; sandbox={SANDBOX_VERSION}",
    }
    schema_name = "run-manifest-v0.1.schema.json"
    if is_a31:
        score_manifest.update(
            source_inference_git_commit=inference_manifest["git_commit"],
            source_inference_config_sha256=inference_manifest["config_sha256"],
            scoring_protocol_version=scoring_protocol,
            scoring_config_sha256=scoring_config_sha256,
            summary_artifact_sha256=summary_artifact_sha256,
        )
        schema_name = "run-manifest-v0.2.schema.json"
    schema = json.loads((repo / "schemas" / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(score_manifest)
    write_json(args.output_dir / "score-manifest.json", score_manifest)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
