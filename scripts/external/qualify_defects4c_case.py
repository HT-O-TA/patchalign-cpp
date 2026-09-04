"""Run one frozen Defects4C qualification case through offline Bubblewrap."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

VERSION = "a3-defects4c-qualification-v1"
PLAN_SHA = "sha256:f07f76ad29c55a01374e12cde8507de623e587a54eac872d3e78f4b69ef12c7d"

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_config(config: dict[str, Any]) -> None:
    if config.get("version") != VERSION:
        raise RuntimeError("wrong Defects4C qualification version")
    if config["source"]["plan_sha256"] != PLAN_SHA or config["source"]["record_count"] != 203:
        raise RuntimeError("Defects4C source plan changed")
    runtime = config["runtime"]
    expected_hashes = {
        "rootfs_archive_sha256": "sha256:46d659c0f3dac1acb0849a17fd0cae2a18848f357847f3db2b61a5858f8f1bab",
        "bash_sha256": "sha256:025cf78cd9d276019e916b97b0decd10cacb14902db8eb9f28233019babfb331",
        "clang_sha256": "sha256:335b5d001032b1df06155f24e449108a78db000d57386bf93683e00138c6d513",
        "cmake_sha256": "sha256:f9145454fdcbf2bb6518db2f93a1594fd778500b8c31cba9ecc66e4547e11f51",
        "ninja_sha256": "sha256:f5b0c00c7cdc229f41d35d36770ff1fb38403cfcac41df481446537c36a02267",
        "bwrap_sha256": "sha256:c69d2514ecdcbb927af4129caccceb8bfc122954e59ab8aa6f9ec50e9a09afda",
    }
    if {key: runtime[key] for key in expected_hashes} != expected_hashes:
        raise RuntimeError("Defects4C runtime identity changed")
    if config["prompt"] != {
        "model_id": "Qwen/Qwen2.5-Coder-7B",
        "model_revision": "0396a76181e127dfc13e5c5ec48a8cee09938b02",
        "model_path": "/mingli01/models/Qwen2.5-Coder-7B",
        "model_config_sha256": "sha256:4e84bfb30ca9a8b765c1a13db4f7aa98be479a2315b1f0c24f53668f95239605",
        "source_prompt_sha256": "sha256:3ef1b7e0867b8616f6becf48c30c92478a04a3111dba5f6398c2887db87808ff",
        "adapter_version": "a3-defects4c-unified-diff-v1",
        "input_mode": "raw_completion",
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
        "scoring_protocol": "a3-scoring-v2",
    }:
        raise RuntimeError("Defects4C prompt contract changed")
    if config["qualification"] != {
        "minimum_qualified": 150,
        "cpu_count_per_case": 8,
        "timeout_seconds": 5400,
        "network": "unshared",
        "rootfs": "read_only",
        "official_source": "read_only",
        "project_code": "read_only",
        "checkout": "read_write",
        "cleanup_build_directory": True,
    }:
        raise RuntimeError("Defects4C qualification policy changed")


def parse_result(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("version") == "a3-defects4c-rootfs-case-v1":
            return value
    raise RuntimeError("rootfs runner did not emit a case result")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--index", type=int, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    plan_path = Path(config["source"]["plan"])
    if sha256_file(plan_path) != config["source"]["plan_sha256"]:
        raise RuntimeError("source plan hash mismatch")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    records = plan["records"]
    if len(records) != config["source"]["record_count"] or not 0 <= args.index < len(records):
        raise RuntimeError("qualification index outside frozen denominator")
    record = records[args.index]
    preflight = json.loads(args.preflight.read_text(encoding="utf-8"))
    current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip()
    if (
        preflight.get("status") != "passed"
        or preflight.get("config_sha256") != sha256_file(args.config)
        or preflight.get("git_commit") != current_commit
    ):
        raise RuntimeError("qualification preflight mismatch")
    if preflight.get("rootfs_archive_sha256") != config["runtime"]["rootfs_archive_sha256"]:
        raise RuntimeError("qualification rootfs preflight mismatch")

    checkpoint = Path(config["progress_directory"]) / "cases" / f"{args.index:03d}.json"
    identity = {
        "version": VERSION, "index": args.index, "record": record,
        "config_sha256": sha256_file(args.config), "preflight_sha256": sha256_file(args.preflight),
    }
    if checkpoint.exists():
        cached = json.loads(checkpoint.read_text(encoding="utf-8"))
        if cached.get("identity") != identity:
            raise RuntimeError("qualification checkpoint identity changed")
        print(json.dumps(cached, ensure_ascii=False, sort_keys=True))
        return

    runtime = config["runtime"]
    repo = Path(__file__).resolve().parents[2]
    command = [
        runtime["bwrap"], "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
        "--bind", runtime["rootfs_directory"], "/",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/root", "--dir", "/tmp/home",
        "--ro-bind", config["source"]["official_directory"], "/src",
        "--bind", config["source"]["checkout_directory"], "/out",
        "--ro-bind", runtime["conda_environment"], "/opt/host-conda",
        "--ro-bind", str(repo), "/patchalign",
        "--remount-ro", "/",
        "--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/host-conda/bin",
        "--setenv", "HOME", "/tmp/home", "--setenv", "PYTHONNOUSERSITE", "1", "--setenv", "LC_ALL", "C.UTF-8",
        "--chdir", "/patchalign",
        "/opt/host-conda/bin/python", "scripts/external/run_defects4c_qualification_case.py",
        "--project", record["project"], "--sha", record["commit_after"],
        "--cpu-count", str(config["qualification"]["cpu_count_per_case"]),
        "--timeout-seconds", str(config["qualification"]["timeout_seconds"]),
    ]
    error = None
    case_result = None
    returncode = None
    try:
        completed = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=config["qualification"]["timeout_seconds"] + 120,
        )
        returncode = completed.returncode
        case_result = parse_result(completed.stdout)
        output_tail = completed.stdout[-8000:]
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        output_tail = getattr(exc, "stdout", "") or ""
        if isinstance(output_tail, bytes):
            output_tail = output_tail.decode("utf-8", errors="replace")
        output_tail = output_tail[-8000:]
    build_path = Path(config["source"]["checkout_directory"]) / record["project"] / f"git_repo_dir_{record['commit_after']}" / f"build_{record['commit_after']}"
    shutil.rmtree(build_path, ignore_errors=True)
    result = {
        "identity": identity, "started_and_finished_at": utc_now(),
        "bwrap_returncode": returncode, "error": error,
        "case_result": case_result, "output_tail": output_tail,
        "qualified": bool(returncode == 0 and case_result and case_result["qualified"]),
        "build_directory_removed": not build_path.exists(),
    }
    write_json_atomic(checkpoint, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
