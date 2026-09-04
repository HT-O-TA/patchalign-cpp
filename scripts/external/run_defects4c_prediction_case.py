"""Execute one model patch inside the frozen offline Defects4C rootfs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

from scripts.external.run_defects4c_qualification_case import (
    OUTPUT_ROOT,
    load_metadata,
    merged_info,
    render,
    status,
    template_path,
)


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_logged(
    command: list[str],
    *,
    cwd: Path,
    stream: Any,
    deadline: float,
    input_text: str | None = None,
) -> dict[str, Any]:
    remaining = max(1.0, deadline - time.monotonic())
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            input=input_text,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=remaining,
        )
        return {
            "returncode": result.returncode,
            "timed_out": False,
            "elapsed_seconds": time.monotonic() - started,
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": None,
            "timed_out": True,
            "elapsed_seconds": time.monotonic() - started,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--role", choices=("m0", "m1_r2"), required=True)
    parser.add_argument("--cpu-count", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    args = parser.parse_args()
    if args.cpu_count < 1 or args.timeout_seconds < 60:
        raise SystemExit(64)

    patch_text = args.patch.read_text(encoding="utf-8")
    started = time.monotonic()
    deadline = started + args.timeout_seconds
    version, project_dir, project_meta, defect = load_metadata(args.project, args.sha)
    info = merged_info(args.project, args.sha, project_meta, defect, args.cpu_count)
    if info["src_file"] != args.source_file:
        raise RuntimeError("qualified source file differs from official metadata")
    repo = Path(info["repo_dir"])
    logs = Path(info["log_dir"])
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"source checkout missing: {repo}")
    logs.mkdir(parents=True, exist_ok=True)

    label = f"{args.sha}_{args.role}"
    test_log = logs / f"test_{label}.log"
    info = {**info, "test_log": str(test_log)}
    rebuild = {**info, "is_rebuild": True, "test_log": str(test_log)}
    build_template = template_path(version, project_dir, info, "build")
    test_template = template_path(version, project_dir, info, "test")
    execution_log = logs / f"prediction_{label}.log"
    for stale in (test_log, test_log.with_suffix(".status"), execution_log):
        stale.unlink(missing_ok=True)
    result: dict[str, Any] = {
        "version": "a3-defects4c-prediction-case-v1",
        "project": args.project,
        "commit_after": args.sha,
        "commit_before": defect["commit_before"],
        "src_file": info["src_file"],
        "role": args.role,
        "patch_sha256": sha256_text(patch_text),
        "terminal_classification": "infrastructure_failed",
        "success": False,
        "timed_out": False,
        "stages": {},
        "log_path": str(execution_log),
    }
    build_path = repo / info["build_dir"]
    try:
        with execution_log.open("w", encoding="utf-8") as stream:
            for command in (
                ["git", "clean", "-dfx"],
                ["git", "checkout", "-f", "--detach", defect["commit_after"]],
                ["git", "submodule", "update", "--init", "--recursive", "--jobs", "1"],
            ):
                stage = run_logged(command, cwd=repo, stream=stream, deadline=deadline)
                if stage["timed_out"] or stage["returncode"] != 0:
                    result["stages"]["prepare"] = stage
                    result["timed_out"] = stage["timed_out"]
                    result["terminal_classification"] = "prepare_timeout" if stage["timed_out"] else "prepare_failed"
                    break
            else:
                result["stages"]["prepare"] = {"returncode": 0, "timed_out": False}
                render(build_template, info, repo / "inplace_build.sh")
                render(build_template, rebuild, repo / "inplace_rebuild.sh")
                render(test_template, info, repo / "inplace_test.sh")
                fixed_build = run_logged(
                    ["bash", "inplace_build.sh", info["build_dir"], str(test_log)],
                    cwd=repo,
                    stream=stream,
                    deadline=deadline,
                )
                result["stages"]["fixed_build"] = fixed_build
                if fixed_build["timed_out"] or fixed_build["returncode"] != 0:
                    result["timed_out"] = fixed_build["timed_out"]
                    result["terminal_classification"] = "fixed_build_timeout" if fixed_build["timed_out"] else "fixed_build_failed"
                else:
                    buggy = run_logged(
                        ["git", "checkout", "-f", defect["commit_before"], "--", info["src_file"]],
                        cwd=repo,
                        stream=stream,
                        deadline=deadline,
                    )
                    result["stages"]["buggy_checkout"] = buggy
                    if buggy["timed_out"] or buggy["returncode"] != 0:
                        result["timed_out"] = buggy["timed_out"]
                        result["terminal_classification"] = "prepare_timeout" if buggy["timed_out"] else "prepare_failed"
                    else:
                        check = run_logged(
                            ["git", "apply", "--recount", "--check", "-"],
                            cwd=repo,
                            stream=stream,
                            deadline=deadline,
                            input_text=patch_text,
                        )
                        result["stages"]["apply_check"] = check
                        if check["timed_out"] or check["returncode"] != 0:
                            result["timed_out"] = check["timed_out"]
                            result["terminal_classification"] = "apply_timeout" if check["timed_out"] else "apply_failed"
                        else:
                            applied = run_logged(
                                ["git", "apply", "--recount", "-"],
                                cwd=repo,
                                stream=stream,
                                deadline=deadline,
                                input_text=patch_text,
                            )
                            result["stages"]["apply"] = applied
                            if applied["timed_out"] or applied["returncode"] != 0:
                                result["timed_out"] = applied["timed_out"]
                                result["terminal_classification"] = "apply_timeout" if applied["timed_out"] else "apply_failed"
                            else:
                                rebuilt = run_logged(
                                    ["bash", "inplace_rebuild.sh", info["build_dir"], str(test_log)],
                                    cwd=repo,
                                    stream=stream,
                                    deadline=deadline,
                                )
                                result["stages"]["build"] = rebuilt
                                if rebuilt["timed_out"] or rebuilt["returncode"] != 0:
                                    result["timed_out"] = rebuilt["timed_out"]
                                    result["terminal_classification"] = "build_timeout" if rebuilt["timed_out"] else "build_failed"
                                else:
                                    tested = run_logged(
                                        ["bash", "inplace_test.sh", info["build_dir"], str(test_log)],
                                        cwd=repo,
                                        stream=stream,
                                        deadline=deadline,
                                    )
                                    test_status = status(test_log.with_suffix(".status"))
                                    result["stages"]["test"] = {**tested, "status_text": test_status}
                                    passed = (
                                        not tested["timed_out"]
                                        and tested["returncode"] == 0
                                        and test_status.lower().startswith("success")
                                    )
                                    result["timed_out"] = tested["timed_out"]
                                    result["terminal_classification"] = (
                                        "success"
                                        if passed
                                        else "test_timeout"
                                        if tested["timed_out"]
                                        else "test_failed"
                                    )
                                    result["success"] = passed
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(build_path, ignore_errors=True)
        result["build_directory_removed"] = not build_path.exists()
        result["elapsed_seconds"] = time.monotonic() - started
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
