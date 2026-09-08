from __future__ import annotations

from pathlib import Path

import pytest

from patchalign.inference import build_prompt, sha256_file, validate_patch, validate_request
from scripts.baseline.run_a3_baseline import build_prompt as frozen_build_prompt


REQUEST = {
    "task_level": "function",
    "allowed_path": "main.cpp",
    "buggy_code": "int main() { return 1; }\n",
    "public_test": {"input": "\n", "output": "0\n"},
}


def test_build_prompt_preserves_frozen_contract() -> None:
    prompt = build_prompt(REQUEST)
    assert prompt.startswith("Repair the localized C++17 program below.\n")
    assert "--- a/main.cpp\n+++ b/main.cpp\n" in prompt
    assert "Task level: function\n" in prompt
    assert prompt.endswith("Unified diff:\n")
    assert prompt == frozen_build_prompt(
        {"task_level": REQUEST["task_level"]},
        REQUEST["buggy_code"],
        REQUEST["public_test"],
        REQUEST["allowed_path"],
    )


def test_request_rejects_path_escape() -> None:
    request = {**REQUEST, "allowed_path": "../main.cpp"}
    with pytest.raises(ValueError, match="safe repository-relative"):
        validate_request(request)


def test_validate_patch_accepts_one_missing_transport_lf() -> None:
    patch = "--- a/main.cpp\n+++ b/main.cpp\n@@ -1 +1 @@\n-old\n+new"
    assert validate_patch(patch, "main.cpp").endswith("+new\n")


def test_validate_patch_rejects_another_file() -> None:
    patch = "--- a/other.cpp\n+++ b/other.cpp\n@@ -1 +1 @@\n-old\n+new\n"
    with pytest.raises(ValueError, match="outside allowed_paths"):
        validate_patch(patch, "main.cpp")


def test_sha256_file_streams_stable_identity(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"patchalign")
    assert sha256_file(artifact) == (
        "sha256:b34c4cb93181020cb2418c2bc6fc98d04b9dd61734486d616cb49bcf5a75c13a"
    )
