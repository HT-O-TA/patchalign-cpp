"""Fail-closed A2 runner; requires bubblewrap for network-isolated execution."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def sandbox_command(case: Path, command: list[str]) -> list[str]:
    return ["bwrap", "--die-with-parent", "--new-session", "--unshare-net", "--ro-bind", "/", "/", "--bind", str(case), "/work", "--chdir", "/work", "--dev", "/dev", "--proc", "/proc", "--"] + command


def run(case: Path, command: list[str], input_text: str = "", timeout: int = 60) -> tuple[str, str, str, float]:
    started = time.monotonic()
    try:
        result = subprocess.run(sandbox_command(case, command), input=input_text, text=True, capture_output=True, timeout=timeout, env={"PATH": os.environ.get("PATH", ""), "HOME": "/tmp", "LANG": "C"})
    except subprocess.TimeoutExpired:
        return "timeout", "", "timeout", time.monotonic() - started
    status = "pass" if result.returncode == 0 else "fail"
    return status, result.stdout, result.stdout + result.stderr, time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if shutil.which("bwrap") is None: raise SystemExit("sandbox_unavailable: bwrap is required; no untrusted code was executed")
    manifest = json.loads((args.holdout_dir / "a2-manifest.json").read_text(encoding="utf-8"))
    results = []
    for item in manifest["cases"]:
        case = args.holdout_dir / "cases" / item["case_id"]
        case_result = {"case_id": item["case_id"], "problem_id": item["problem_id"], "task_level": item["task_level"], "versions": {}}
        for version in ("buggy", "fixed"):
            shutil.copyfile(case / f"{version}.cpp", case / "main.cpp")
            status, _stdout, output, elapsed = run(case, ["/usr/bin/g++", "-std=c++17", "-O2", "main.cpp", "-o", "main"], timeout=120)
            version_result = {"compile": {"status": status, "elapsed_seconds": elapsed}}
            if status == "pass":
                tests = {}
                for line in (case / "tests.jsonl").read_text(encoding="utf-8").splitlines():
                    test = json.loads(line)
                    tests[test["id"]] = test
                suites = json.loads((case / "test-partition.json").read_text(encoding="utf-8")); version_result["suites"] = {}
                for suite, ids in suites.items():
                    outcomes = []
                    for test_id in ids:
                        test = tests[str(test_id)] if str(test_id) in tests else tests[test_id]
                        test_status, actual, output, test_elapsed = run(case, ["/work/main"], test["input"], 60)
                        outcomes.append({"test_id": test_id, "status": test_status, "matched": test_status == "pass" and actual.strip() == test["output"].strip(), "elapsed_seconds": test_elapsed, "error_tail": output[-1000:] if test_status != "pass" else ""})
                    version_result["suites"][suite] = outcomes
            else: version_result["compile_error"] = output[-2000:]
            version_result["summary"] = {suite: {"total": len(outcomes), "matched": sum(outcome["matched"] for outcome in outcomes), "all_matched": all(outcome["matched"] for outcome in outcomes)} for suite, outcomes in version_result.get("suites", {}).items()}
            case_result["versions"][version] = version_result
        buggy = case_result["versions"]["buggy"]
        fixed = case_result["versions"]["fixed"]
        case_result["acceptance"] = {
            "buggy_regression_failure_observed": bool(buggy.get("summary", {}).get("regression", {}).get("matched", 0) < buggy.get("summary", {}).get("regression", {}).get("total", 0)),
            "fixed_regression_all_matched": fixed.get("summary", {}).get("regression", {}).get("all_matched", False),
            "fixed_all_tests_matched": all(summary["all_matched"] for summary in fixed.get("summary", {}).values()),
        }
        results.append(case_result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(result, ensure_ascii=False, sort_keys=True) for result in results) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(results), "output": str(args.output), "buggy_regression_failures": sum(result["acceptance"]["buggy_regression_failure_observed"] for result in results), "fixed_regression_all_matched": sum(result["acceptance"]["fixed_regression_all_matched"] for result in results), "fixed_all_tests_matched": sum(result["acceptance"]["fixed_all_tests_matched"] for result in results)}, sort_keys=True))


if __name__ == "__main__": main()
