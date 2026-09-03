"""Fail-closed A2 runner using an independently validated Bubblewrap boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

try:
    from .a2_output_matcher import matcher_metadata, outputs_match
    from .a2_sandbox_runtime import SANDBOX_VERSION, public_result, resolve_bwrap, run_sandboxed
except ImportError:
    from a2_output_matcher import matcher_metadata, outputs_match
    from a2_sandbox_runtime import SANDBOX_VERSION, public_result, resolve_bwrap, run_sandboxed


def load_tests(case: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[Any]]]:
    tests: dict[str, dict[str, Any]] = {}
    for line in (case / "tests.jsonl").read_text(encoding="utf-8").splitlines():
        test = json.loads(line)
        tests[str(test["id"])] = test
    suites = json.loads((case / "test-partition.json").read_text(encoding="utf-8"))
    return tests, suites


def sanitizer_record(item: dict[str, Any]) -> dict[str, Any]:
    if "sanitizer_applicable" not in item:
        raise RuntimeError("A2 manifest case is missing sanitizer_applicable")
    if item["sanitizer_applicable"] is not False:
        raise RuntimeError("this A2 runner has no configured sanitizer command")
    if item.get("sanitizer_status") != "not_applicable":
        raise RuntimeError("non-applicable sanitizer must have not_applicable status")
    return {"sanitizer_applicable": False, "status": "not_applicable"}


def resolve_case(root: Path, case_id: object, *, require_partition: bool = True) -> Path:
    if not isinstance(case_id, str) or not case_id or Path(case_id).name != case_id:
        raise RuntimeError(f"unsafe case_id: {case_id!r}")
    cases_root = (root / "cases").resolve(strict=True)
    candidate = cases_root / case_id
    if candidate.is_symlink():
        raise RuntimeError(f"case directory must not be a symlink: {candidate}")
    case = candidate.resolve(strict=True)
    if case.parent != cases_root or not case.is_dir():
        raise RuntimeError(f"case escaped root: {case}")
    filenames = ["tests.jsonl"]
    if require_partition:
        filenames.append("test-partition.json")
    for filename in filenames:
        path = case / filename
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"unsafe or missing case metadata: {path}")
    return case


def execute_version(
    case: Path,
    version: str,
    problem_id: str,
    bwrap: Path,
    tests: dict[str, dict[str, Any]],
    suites: dict[str, list[Any]],
    *,
    stop_on_timeout: bool = False,
) -> dict[str, Any]:
    source = case / f"{version}.cpp"
    if not source.is_file() or source.is_symlink():
        raise RuntimeError(f"unsafe or missing source path: {source}")
    with tempfile.TemporaryDirectory(prefix=f"patchalign-a2-build-{version}-") as directory:
        build_workspace = Path(directory)
        shutil.copyfile(source, build_workspace / "main.cpp")
        compile_result = run_sandboxed(
            build_workspace,
            ["/usr/bin/g++", "-std=c++17", "-O2", "main.cpp", "-o", "main"],
            bwrap,
            timeout=120,
        )
        version_result: dict[str, Any] = {"compile": public_result(compile_result)}
        if compile_result["status"] != "pass":
            version_result["compile_error_tail"] = compile_result["stderr"][-2000:]
            version_result["summary"] = {}
            return version_result
        executable = build_workspace / "main"
        if not executable.is_file() or executable.is_symlink():
            raise RuntimeError(f"compiler did not create a regular executable: {executable}")
        version_result["suites"] = {}
        for suite, ids in suites.items():
            outcomes = []
            for test_id in ids:
                test = tests[str(test_id)]
                with tempfile.TemporaryDirectory(prefix="patchalign-a2-test-") as test_directory:
                    test_workspace = Path(test_directory)
                    shutil.copyfile(executable, test_workspace / "main")
                    (test_workspace / "main").chmod(0o500)
                    test_result = run_sandboxed(
                        test_workspace,
                        ["/work/main"],
                        bwrap,
                        input_text=test["input"],
                        timeout=60,
                    )
                matched = test_result["status"] == "pass" and outputs_match(
                    test["output"], test_result["stdout"], problem_id
                )
                outcome = {"test_id": test_id, "matched": matched, **public_result(test_result)}
                if test_result["status"] != "pass":
                    outcome["error_tail"] = test_result["stderr"][-1000:]
                outcomes.append(outcome)
                if stop_on_timeout and test_result["timed_out"]:
                    break
            version_result["suites"][suite] = outcomes
    version_result["summary"] = {
        suite: {
            "total": len(outcomes),
            "matched": sum(outcome["matched"] for outcome in outcomes),
            "all_matched": bool(outcomes) and all(outcome["matched"] for outcome in outcomes),
        }
        for suite, outcomes in version_result["suites"].items()
    }
    return version_result


def acceptance_record(case_result: dict[str, Any]) -> dict[str, bool]:
    buggy_suites = case_result["versions"]["buggy"].get("suites", {})
    fixed_suites = case_result["versions"]["fixed"].get("suites", {})
    regression_buggy = buggy_suites.get("regression", [])
    target_buggy = buggy_suites.get("public", []) + buggy_suites.get("hidden", [])
    all_fixed = fixed_suites.get("regression", []) + fixed_suites.get("public", []) + fixed_suites.get("hidden", [])
    fixed_all = bool(all_fixed) and all(item["matched"] for item in all_fixed)
    partition_contract = (
        len(regression_buggy) >= 3
        and len(buggy_suites.get("public", [])) >= 1
        and len(buggy_suites.get("hidden", [])) >= 1
        and all(item["matched"] for item in regression_buggy)
        and bool(target_buggy)
        and all(not item["matched"] for item in target_buggy)
        and fixed_all
    )
    return {
        "buggy_target_failure_observed": bool(target_buggy) and any(not item["matched"] for item in target_buggy),
        "fixed_all_tests_matched": fixed_all,
        "partition_contract_satisfied": partition_contract,
    }


def execute_case(item: dict[str, Any], case: Path, bwrap: Path, suites: dict[str, list[Any]]) -> dict[str, Any]:
    tests = {
        str(test["id"]): test
        for test in map(json.loads, (case / "tests.jsonl").read_text(encoding="utf-8").splitlines())
    }
    case_result: dict[str, Any] = {
        "schema_version": "0.2.0-draft",
        "case_id": item["case_id"],
        "problem_id": item["problem_id"],
        "task_level": item["task_level"],
        "sandbox": {"backend": "bubblewrap", "policy_version": SANDBOX_VERSION},
        "output_matcher": matcher_metadata(),
        "sanitizer": sanitizer_record(item),
        "versions": {},
    }
    for version in ("buggy", "fixed"):
        case_result["versions"][version] = execute_version(
            case, version, str(item["problem_id"]), bwrap, tests, suites
        )
    case_result["acceptance"] = acceptance_record(case_result)
    return case_result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bwrap", type=Path, default=shutil.which("bwrap"))
    args = parser.parse_args()
    if args.bwrap is None:
        raise SystemExit("sandbox_unavailable: bwrap is required; no untrusted code was executed")
    bwrap = resolve_bwrap(args.bwrap)
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite execution artifact: {args.output}")
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "a2-execution-v0.2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)
    manifest = json.loads((args.holdout_dir / "a2-manifest.json").read_text(encoding="utf-8"))
    results = []
    for item in manifest["cases"]:
        case = resolve_case(args.holdout_dir, item["case_id"])
        _, suites = load_tests(case)
        case_result = execute_case(item, case, bwrap, suites)
        validator.validate(case_result)
        results.append(case_result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(result, ensure_ascii=False, sort_keys=True) for result in results) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "cases": len(results),
        "output": str(args.output),
        "buggy_target_failures": sum(result["acceptance"]["buggy_target_failure_observed"] for result in results),
        "fixed_all_tests_matched": sum(result["acceptance"]["fixed_all_tests_matched"] for result in results),
        "partition_contract_satisfied": sum(result["acceptance"]["partition_contract_satisfied"] for result in results),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
