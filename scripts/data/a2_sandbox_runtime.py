"""Minimal Bubblewrap runtime used by the A2 replay tools."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import time
from typing import Any, Sequence


SANDBOX_VERSION = "bubblewrap-rootless-v1"
DEFAULT_OUTPUT_LIMIT_BYTES = 1_048_576
DEFAULT_MEMORY_LIMIT_BYTES = 2 * 1024**3


class SandboxUnavailable(RuntimeError):
    """Raised when the required sandbox executable or host paths are unavailable."""


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def resolve_bwrap(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise SandboxUnavailable(f"bwrap is not executable: {path}")
    return path


def sandbox_command(
    workspace: str | Path, command: Sequence[str], bwrap: str | Path
) -> list[str]:
    """Build a rootless, networkless command without exposing host data roots."""

    work = Path(workspace).resolve(strict=True)
    if not work.is_dir():
        raise ValueError(f"workspace is not a directory: {work}")
    if not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("command must contain non-empty strings")

    args = [
        str(resolve_bwrap(bwrap)),
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-net",
        "--unshare-uts",
        "--uid",
        "0",
        "--gid",
        "0",
        "--cap-drop",
        "ALL",
        "--hostname",
        "patchalign-a2",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "LANG",
        "C",
        "--setenv",
        "LC_ALL",
        "C",
    ]
    for host_path in (Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64")):
        if host_path.exists():
            args.extend(("--ro-bind", str(host_path), str(host_path)))
    ld_cache = Path("/etc/ld.so.cache")
    if ld_cache.exists():
        args.extend(("--dir", "/etc", "--ro-bind", str(ld_cache), str(ld_cache)))
    args.extend(
        (
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/work",
            "--bind",
            str(work),
            "/work",
            "--chdir",
            "/work",
            "--",
            *command,
        )
    )
    return args


def _limit_process(timeout: int, memory_limit_bytes: int, output_limit_bytes: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (timeout + 1, timeout + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit_bytes, output_limit_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def run_sandboxed(
    workspace: str | Path,
    command: Sequence[str],
    bwrap: str | Path,
    *,
    input_text: str = "",
    timeout: int = 60,
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
) -> dict[str, Any]:
    """Run one bounded command and return capped output plus reproducibility metadata."""

    if timeout < 1 or memory_limit_bytes < 1 or output_limit_bytes < 1:
        raise ValueError("resource limits must be positive")
    argv = sandbox_command(workspace, command, bwrap)
    started = time.monotonic()
    timed_out = False
    with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(
        mode="w+b"
    ) as stderr_file:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
            preexec_fn=lambda: _limit_process(timeout, memory_limit_bytes, output_limit_bytes),
        )
        try:
            process.communicate(input=input_text.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(output_limit_bytes + 1)
        stderr = stderr_file.read(output_limit_bytes + 1)

    stdout_truncated = len(stdout) > output_limit_bytes
    stderr_truncated = len(stderr) > output_limit_bytes
    stdout = stdout[:output_limit_bytes]
    stderr = stderr[:output_limit_bytes]
    status = "timeout" if timed_out else "pass" if process.returncode == 0 else "fail"
    return {
        "status": status,
        "exit_code": None if timed_out else process.returncode,
        "timed_out": timed_out,
        "elapsed_seconds": time.monotonic() - started,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "stdout_sha256": _sha256(stdout),
        "stderr_sha256": _sha256(stderr),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "sandbox_backend": "bubblewrap",
        "sandbox_version": SANDBOX_VERSION,
    }


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove raw streams before persisting a result record."""

    return {key: value for key, value in result.items() if key not in {"stdout", "stderr"}}
