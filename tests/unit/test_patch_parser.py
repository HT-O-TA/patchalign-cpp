from __future__ import annotations

import pytest

from patchalign.evaluation.patches import (
    PatchParseError,
    PatchPolicyError,
    enforce_patch_policy,
    normalize_terminal_lf,
    parse_unified_diff,
)


def test_parser_accepts_context_and_multiple_hunks() -> None:
    patch = """diff --git a/src/add.cpp b/src/add.cpp
index 1111111..2222222 100644
--- a/src/add.cpp
+++ b/src/add.cpp
@@ -1,3 +1,3 @@
 context one
-old one
+new one
 context two
@@ -10,2 +10,3 @@ helper
 context three
-old two
+new two
+added two
"""
    parsed = parse_unified_diff(patch)
    assert parsed.files[0].hunk_count == 2
    assert enforce_patch_policy(parsed, ["src/add.cpp"]) == ("src/add.cpp",)


@pytest.mark.parametrize(
    "raw_text",
    (
        "explanation\n--- a/src/add.cpp\n+++ b/src/add.cpp\n@@ -1 +1 @@\n-a\n+b\n",
        "```diff\n--- a/src/add.cpp\n+++ b/src/add.cpp\n@@ -1 +1 @@\n-a\n+b\n```\n",
        "--- a/src/add.cpp\n+++ b/src/add.cpp\nnot-a-hunk\n",
        "--- a/src/add.cpp\n+++ b/src/add.cpp\n@@ malformed @@\n-a\n+b\n",
    ),
)
def test_parser_strictly_rejects_malformed_or_wrapped_output(raw_text: str) -> None:
    with pytest.raises(PatchParseError):
        parse_unified_diff(raw_text)


@pytest.mark.parametrize(
    "patch,allowed_paths",
    (
        ("--- /tmp/add.cpp\n+++ b/src/add.cpp\n@@ -1 +1 @@\n-a\n+b\n", ["src/add.cpp"]),
        ("--- a/../add.cpp\n+++ b/../add.cpp\n@@ -1 +1 @@\n-a\n+b\n", ["../add.cpp"]),
        ("--- a/src/add.cpp\n+++ b/src/other.cpp\n@@ -1 +1 @@\n-a\n+b\n", ["src/add.cpp"]),
        ("--- a/tests/test.cpp\n+++ b/tests/test.cpp\n@@ -1 +1 @@\n-a\n+b\n", ["src/add.cpp"]),
    ),
)
def test_policy_rejects_unsafe_or_disallowed_paths(
    patch: str, allowed_paths: list[str]
) -> None:
    with pytest.raises(PatchPolicyError):
        enforce_patch_policy(parse_unified_diff(patch), allowed_paths)


def test_policy_rejects_binary_patch() -> None:
    patch = """diff --git a/src/add.cpp b/src/add.cpp
GIT binary patch
literal 1
abc
"""
    with pytest.raises(PatchPolicyError, match="binary"):
        enforce_patch_policy(parse_unified_diff(patch), ["src/add.cpp"])


def test_policy_rejects_multiple_plain_unified_diff_sections() -> None:
    patch = """--- a/src/add.cpp
+++ b/src/add.cpp
@@ -1 +1 @@
-old
+new
--- a/tests/test.cpp
+++ b/tests/test.cpp
@@ -1 +1 @@
-old test


def test_terminal_lf_normalization_appends_exactly_one_lf() -> None:
    raw = "--- a/main.cpp\n+++ b/main.cpp\n@@ -1 +1 @@\n-old\n+new"
    normalized, added = normalize_terminal_lf(raw)
    assert added is True
    assert normalized == raw + "\n"


@pytest.mark.parametrize("raw", ("", "already\n", "windows\r\n"))
def test_terminal_lf_normalization_preserves_already_terminated_text(raw: str) -> None:
    normalized, added = normalize_terminal_lf(raw)
    assert added is False
    assert normalized == raw


def test_terminal_lf_normalization_does_not_strip_or_recover_content() -> None:
    raw = "explanation\n\n```diff\n--- a/main.cpp  "
    normalized, added = normalize_terminal_lf(raw)
    assert added is True
    assert normalized == raw + "\n"

+new test
"""
    parsed = parse_unified_diff(patch)
    assert len(parsed.files) == 2
    with pytest.raises(PatchPolicyError, match="exactly one"):
        enforce_patch_policy(parsed, ["src/add.cpp"])
