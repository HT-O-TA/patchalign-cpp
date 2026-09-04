"""Fail-closed preflight for offline Defects4C qualification."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from scripts.external.qualify_defects4c_case import validate_config
from scripts.training.a3_formal_common import require, write_json


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "qualification preflight requires clean worktree")
    require(not args.report.exists(), "refusing to overwrite qualification preflight")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    runtime, source = config["runtime"], config["source"]
    rootfs = Path(runtime["rootfs_directory"])
    checks = {
        "rootfs_archive_sha256": sha256_file(Path(runtime["rootfs_archive"])),
        "bash_sha256": sha256_file(rootfs / "bin/bash"),
        "clang_sha256": sha256_file(rootfs / "usr/local/bin/clang-16"),
        "cmake_sha256": sha256_file(rootfs / "usr/local/bin/cmake"),
        "ninja_sha256": sha256_file(rootfs / "usr/bin/ninja"),
        "bwrap_sha256": sha256_file(Path(runtime["bwrap"])),
    }
    for key, observed in checks.items():
        require(observed == runtime[key], f"runtime hash mismatch: {key}")
    require(sha256_file(Path(source["plan"])) == source["plan_sha256"], "source plan hash mismatch")
    require(Path(source["official_directory"]).is_dir(), "official source directory missing")
    require(Path(source["checkout_directory"]).is_dir(), "checkout directory missing")
    require(Path(runtime["conda_environment"]).is_dir(), "Conda environment missing")
    command = [
        runtime["bwrap"], "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
        "--ro-bind", runtime["rootfs_directory"], "/",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/root", "--dir", "/tmp/home",
        "--ro-bind", source["official_directory"], "/src",
        "--bind", source["checkout_directory"], "/out",
        "--ro-bind", runtime["conda_environment"], "/opt/host-conda",
        "--ro-bind", str(repo), "/patchalign",
        "--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/host-conda/bin",
        "--setenv", "HOME", "/tmp/home", "--setenv", "PYTHONNOUSERSITE", "1",
        "--chdir", "/patchalign", "/bin/bash", "-c",
        "test -x /usr/local/bin/clang-16 && test -f scripts/external/run_defects4c_qualification_case.py && /opt/host-conda/bin/python -c 'import jinja2; print(jinja2.__version__)' && ! touch /src/patchalign-readonly-probe 2>/dev/null && ! touch /patchalign/patchalign-readonly-probe 2>/dev/null && ! timeout 3 bash -c '</dev/tcp/github.com/443' 2>/dev/null",
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    require(result.returncode == 0, "offline rootfs smoke failed: " + result.stdout[-2000:])
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    report = {
        "version": "a3-defects4c-qualification-preflight-v1",
        "status": "passed", "checked_at": utc_now(), "git_commit": commit,
        "config_sha256": sha256_file(args.config), **checks,
        "source_plan_sha256": source["plan_sha256"],
        "rootfs_smoke_output": result.stdout.strip(),
        "network_unshared_probe": "tcp_connection_failed_as_required",
        "read_only_probes": "official_source_and_project_code_rejected_writes",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
