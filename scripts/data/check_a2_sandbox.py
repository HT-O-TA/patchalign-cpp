"""Fail-closed self-test for the A2 Bubblewrap boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

try:
    from .a2_sandbox_runtime import (
        SANDBOX_VERSION,
        public_result,
        resolve_bwrap,
        run_sandboxed,
    )
except ImportError:
    from a2_sandbox_runtime import SANDBOX_VERSION, public_result, resolve_bwrap, run_sandboxed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bwrap", type=Path, required=True)
    args = parser.parse_args()
    bwrap = resolve_bwrap(args.bwrap)
    version = subprocess.run(
        [str(bwrap), "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()

    with tempfile.TemporaryDirectory(prefix="patchalign-a2-selftest-") as directory:
        workspace = Path(directory)
        (workspace / "probe.txt").write_text("ok\n", encoding="utf-8")
        boundary = run_sandboxed(
            workspace,
            [
                "/bin/sh",
                "-c",
                "set -eu; "
                "test \"$(cat /work/probe.txt)\" = ok; "
                "touch /work/workspace-writable; "
                "touch /tmp/tmp-writable; "
                "test ! -e /home; "
                "test ! -e /mingli01; "
                "if touch /usr/patchalign-must-not-write 2>/dev/null; then exit 41; fi; "
                "cat /proc/net/dev",
            ],
            bwrap,
            timeout=10,
        )
        workspace_writable = (workspace / "workspace-writable").exists()
        (workspace / "main.cpp").write_text(
            '#include <iostream>\nint main() { std::cout << "sandbox-ok\\n"; }\n',
            encoding="utf-8",
        )
        compile_result = run_sandboxed(
            workspace,
            ["/usr/bin/g++", "-std=c++17", "main.cpp", "-o", "main"],
            bwrap,
            timeout=30,
        )
        execute_result = (
            run_sandboxed(workspace, ["/work/main"], bwrap, timeout=10)
            if compile_result["status"] == "pass"
            else {"status": "not_run", "stdout": "", "stderr": ""}
        )

    interfaces = []
    for line in boundary["stdout"].splitlines()[2:]:
        if ":" in line:
            interfaces.append(line.split(":", 1)[0].strip())
    boundary_passed = boundary["status"] == "pass"
    checks = {
        "boundary_command_passed": boundary_passed,
        "workspace_writable": workspace_writable,
        "network_interfaces_only_loopback": interfaces == ["lo"],
        "host_home_hidden": boundary_passed,
        "host_mingli01_hidden": boundary_passed,
        "system_paths_read_only": boundary_passed,
        "private_tmp": boundary_passed,
        "controlled_cpp_compiles": compile_result["status"] == "pass",
        "controlled_cpp_runs": execute_result["status"] == "pass"
        and execute_result["stdout"] == "sandbox-ok\n",
    }
    report = {
        "sandbox_backend": "bubblewrap",
        "sandbox_policy_version": SANDBOX_VERSION,
        "bubblewrap_version": version,
        "network_interfaces": interfaces,
        "checks": checks,
        "passed": all(checks.values()),
        "boundary_result": public_result(boundary),
        "compile_result": public_result(compile_result),
        "execute_result": public_result(execute_result)
        if execute_result["status"] != "not_run"
        else {"status": "not_run"},
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if not report["passed"]:
        raise SystemExit("sandbox self-test failed; no untrusted code was executed")


if __name__ == "__main__":
    main()
