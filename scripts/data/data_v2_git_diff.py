"""Fail-closed parser for one verified Git zero-context text diff."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


MAX_DIFF_BYTES = 16 * 1024 * 1024
_HUNK = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)


@dataclass(frozen=True)
class ZeroContextDiff:
    old_ranges: tuple[tuple[int, int], ...]
    new_ranges: tuple[tuple[int, int], ...]
    additions: int
    deletions: int
    patch_sha256: str


def parse_zero_context_diff(payload: bytes) -> ZeroContextDiff:
    """Parse output from Git diff invoked with ``--unified=0 --no-renames``.

    Repository/path identity is verified separately with NUL-delimited Git
    plumbing.  This parser proves that exactly one modified text-file section is
    present and that every hunk's declared old/new counts match its body.
    """

    if not payload or len(payload) > MAX_DIFF_BYTES:
        raise ValueError("diff is empty or exceeds byte limit")
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("diff is not UTF-8 text") from error
    if sum(line.startswith("diff --git ") for line in lines) != 1:
        raise ValueError("diff must contain exactly one file section")
    forbidden_prefixes = (
        "new file mode ",
        "deleted file mode ",
        "old mode ",
        "new mode ",
        "similarity index ",
        "dissimilarity index ",
        "rename from ",
        "rename to ",
        "copy from ",
        "copy to ",
        "Binary files ",
        "GIT binary patch",
    )

    old_header = new_header = 0
    old_ranges: list[tuple[int, int]] = []
    new_ranges: list[tuple[int, int]] = []
    current: tuple[int, int, int, int] | None = None
    old_seen = new_seen = 0

    def finish_hunk() -> None:
        nonlocal current, old_seen, new_seen
        if current is None:
            return
        old_start, old_count, new_start, new_count = current
        if old_seen != old_count or new_seen != new_count:
            raise ValueError("diff hunk body/count mismatch")
        old_ranges.append((old_start, old_count))
        new_ranges.append((new_start, new_count))
        current = None
        old_seen = new_seen = 0

    for line in lines:
        if current is not None:
            match = _HUNK.fullmatch(line)
            if match:
                finish_hunk()
                current = _parse_hunk(match)
                continue
            if line.startswith("-"):
                old_seen += 1
                continue
            if line.startswith("+"):
                new_seen += 1
                continue
            if line == "\\ No newline at end of file":
                continue
            raise ValueError("zero-context hunk contains context/metadata")

        match = _HUNK.fullmatch(line)
        if match:
            if old_header != 1 or new_header != 1:
                raise ValueError("diff hunk appears before unique file headers")
            current = _parse_hunk(match)
            continue
        if line.startswith(forbidden_prefixes):
            raise ValueError("new/deleted/renamed/binary/mode diff is not supported")
        if line.startswith("--- "):
            old_header += 1
            if line == "--- /dev/null":
                raise ValueError("new files are not supported")
            continue
        if line.startswith("+++ "):
            new_header += 1
            if line == "+++ /dev/null":
                raise ValueError("deleted files are not supported")
            continue
        if line.startswith("diff --git ") or line.startswith("index "):
            continue
        raise ValueError(f"unsupported diff metadata: {line[:40]}")
    finish_hunk()
    if old_header != 1 or new_header != 1 or not old_ranges:
        raise ValueError("diff lacks unique headers or hunks")
    for ranges in (old_ranges, new_ranges):
        previous_start = -1
        for start, _count in ranges:
            if start < previous_start:
                raise ValueError("diff hunks are not ordered")
            previous_start = start
    return ZeroContextDiff(
        old_ranges=tuple(old_ranges),
        new_ranges=tuple(new_ranges),
        additions=sum(count for _start, count in new_ranges),
        deletions=sum(count for _start, count in old_ranges),
        patch_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def _parse_hunk(match: re.Match[str]) -> tuple[int, int, int, int]:
    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) is not None else 1
    new_start = int(match.group(3))
    new_count = int(match.group(4)) if match.group(4) is not None else 1
    if old_count < 0 or new_count < 0:
        raise ValueError("negative hunk count")
    if (old_count and old_start < 1) or (new_count and new_start < 1):
        raise ValueError("non-empty hunk has invalid start")
    return old_start, old_count, new_start, new_count
