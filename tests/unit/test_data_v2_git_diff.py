from __future__ import annotations

import pytest

from scripts.data.data_v2_cpp_context import anchors_from_old_ranges
from scripts.data.data_v2_git_diff import parse_zero_context_diff


def test_parses_replacement_and_insertion_with_exact_old_anchors() -> None:
    patch = b'''diff --git a/src/fix.cpp b/src/fix.cpp
index 1111111..2222222 100644
--- a/src/fix.cpp
+++ b/src/fix.cpp
@@ -4,2 +4,2 @@ int repair() {
-  old_one();
-  old_two();
+  new_one();
+  new_two();
@@ -10,0 +11,1 @@ int repair() {
+  inserted();
'''
    parsed = parse_zero_context_diff(patch)
    assert parsed.old_ranges == ((4, 2), (10, 0))
    assert parsed.new_ranges == ((4, 2), (11, 1))
    assert (parsed.additions, parsed.deletions) == (3, 2)
    assert anchors_from_old_ranges(12, parsed.old_ranges) == (4, 5, 10, 11)


def test_deleted_content_that_looks_like_header_is_counted_inside_hunk() -> None:
    patch = b'''diff --git a/x.cpp b/x.cpp
index 1..2 100644
--- a/x.cpp
+++ b/x.cpp
@@ -1 +1 @@
---- literal
++++ replacement
'''
    parsed = parse_zero_context_diff(patch)
    assert (parsed.additions, parsed.deletions) == (1, 1)


def test_rejects_context_count_mismatch_and_multiple_files() -> None:
    bad_payloads = [
        b'''diff --git a/x.cpp b/x.cpp
index 1..2 100644
--- a/x.cpp
+++ b/x.cpp
@@ -1 +1 @@
 context
''',
        b'''diff --git a/x.cpp b/x.cpp
index 1..2 100644
--- a/x.cpp
+++ b/x.cpp
@@ -1,2 +1 @@
-one
+two
''',
        b'''diff --git a/x.cpp b/x.cpp
diff --git a/y.cpp b/y.cpp
''',
    ]
    for payload in bad_payloads:
        with pytest.raises(ValueError):
            parse_zero_context_diff(payload)


def test_rejects_new_deleted_binary_rename_and_mode_changes() -> None:
    metadata = [
        "new file mode 100644",
        "deleted file mode 100644",
        "GIT binary patch",
        "rename from old.cpp",
        "old mode 100644",
    ]
    for item in metadata:
        patch = (
            "diff --git a/x.cpp b/x.cpp\n"
            + item
            + "\n--- a/x.cpp\n+++ b/x.cpp\n@@ -1 +1 @@\n-one\n+two\n"
        ).encode()
        with pytest.raises(ValueError, match="not supported"):
            parse_zero_context_diff(patch)
