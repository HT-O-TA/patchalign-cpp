from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.data.a2_sandbox_runtime import (
    SandboxUnavailable,
    public_result,
    resolve_bwrap,
    sandbox_command,
)
from scripts.data.run_a2_cases import resolve_case, sanitizer_record


def flag_pairs(arguments: list[str], flag: str) -> list[tuple[str, str]]:
    return [
        (arguments[index + 1], arguments[index + 2])
        for index, value in enumerate(arguments)
        if value == flag
    ]


def test_sandbox_command_uses_minimal_rootless_boundary(tmp_path: Path) -> None:
    arguments = sandbox_command(tmp_path, ["/bin/true"], "/bin/true")

    assert "--unshare-user" in arguments
    assert "--unshare-net" in arguments
    assert "--unshare-pid" in arguments
    assert "--cap-drop" in arguments
    assert ("/", "/") not in flag_pairs(arguments, "--ro-bind")
    assert all(
        source not in {"/home", "/mingli01"}
        for source, _ in flag_pairs(arguments, "--ro-bind")
    )
    assert (str(tmp_path.resolve()), "/work") in flag_pairs(arguments, "--bind")
    assert arguments[arguments.index("--tmpfs") + 1] == "/tmp"
    assert arguments[-2:] == ["--", "/bin/true"]


def test_sandbox_command_rejects_empty_command(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="command"):
        sandbox_command(tmp_path, [], "/bin/true")


def test_resolve_bwrap_rejects_missing_executable(tmp_path: Path) -> None:
    with pytest.raises(SandboxUnavailable, match="not executable"):
        resolve_bwrap(tmp_path / "missing-bwrap")


def test_public_result_removes_raw_output() -> None:
    result = public_result({"status": "pass", "stdout": "secret", "stderr": "error"})
    assert result == {"status": "pass"}


def test_sanitizer_record_is_explicit_and_fail_closed() -> None:
    assert sanitizer_record(
        {"sanitizer_applicable": False, "sanitizer_status": "not_applicable"}
    ) == {"sanitizer_applicable": False, "status": "not_applicable"}
    with pytest.raises(RuntimeError, match="missing sanitizer_applicable"):
        sanitizer_record({})
    with pytest.raises(RuntimeError, match="no configured sanitizer"):
        sanitizer_record({"sanitizer_applicable": True, "sanitizer_status": "not_run"})


def make_case(root: Path, name: str = "case-1") -> Path:
    case = root / "cases" / name
    case.mkdir(parents=True)
    (case / "tests.jsonl").write_text("", encoding="utf-8")
    (case / "test-partition.json").write_text("{}\n", encoding="utf-8")
    return case


def test_resolve_case_accepts_regular_case_directory(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    assert resolve_case(tmp_path, "case-1") == case.resolve()


def test_resolve_case_rejects_parent_escape(tmp_path: Path) -> None:
    (tmp_path / "cases").mkdir()
    with pytest.raises(RuntimeError, match="unsafe case_id"):
        resolve_case(tmp_path, "../escape")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not generally available")
def test_resolve_case_rejects_directory_symlink(tmp_path: Path) -> None:
    target = make_case(tmp_path, "real")
    (tmp_path / "cases" / "linked").symlink_to(target, target_is_directory=True)
    with pytest.raises(RuntimeError, match="must not be a symlink"):
        resolve_case(tmp_path, "linked")
