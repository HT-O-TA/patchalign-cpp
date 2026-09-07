"""Deterministic C++ change anchors and Clang-AST context selection for Data-v2.

This module deliberately does not invoke a compiler.  The content qualification
runner supplies JSON emitted by the frozen Clang binary and the exact source
bytes; keeping selection pure makes the result independently replayable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


FUNCTION_KINDS = frozenset(
    {
        "FunctionDecl",
        "CXXMethodDecl",
        "CXXConstructorDecl",
        "CXXDestructorDecl",
        "CXXConversionDecl",
    }
)


@dataclass(frozen=True, order=True)
class FunctionSpan:
    start_line: int
    end_line: int
    kind: str
    name: str


@dataclass(frozen=True)
class FileWindow:
    start_line: int
    end_line: int
    core_start_line: int
    core_end_line: int
    context_before: int
    context_after: int


def anchors_from_old_ranges(
    total_old_lines: int, old_ranges: Iterable[tuple[int, int]]
) -> tuple[int, ...]:
    """Convert verified git zero-context diff old ranges to old-side anchors.

    A positive count owns the exact deleted/replaced lines.  A zero-count
    insertion is anchored to both adjacent old lines when they exist, preventing
    an insertion at a function boundary from being called an in-function edit.
    """

    if total_old_lines < 0:
        raise ValueError("total_old_lines must not be negative")
    anchors: set[int] = set()
    saw_range = False
    for old_start, old_count in old_ranges:
        saw_range = True
        if old_count < 0:
            raise ValueError("old range count must not be negative")
        if old_count:
            if old_start < 1 or old_start + old_count - 1 > total_old_lines:
                raise ValueError("old range is outside source")
            anchors.update(range(old_start, old_start + old_count))
            continue
        if old_start < 0 or old_start > total_old_lines:
            raise ValueError("insertion position is outside source")
        if not total_old_lines:
            anchors.add(1)
        else:
            if old_start > 0:
                anchors.add(old_start)
            if old_start < total_old_lines:
                anchors.add(old_start + 1)
    if not saw_range:
        return ()
    return tuple(sorted(anchors))


def _normalized_path(value: str) -> str:
    return str(PurePosixPath(value.replace("\\", "/")))


def _offset_line(source_bytes: bytes, offset: int, *, end_token_length: int = 0) -> int | None:
    if offset < 0 or offset > len(source_bytes):
        return None
    if end_token_length:
        offset = min(len(source_bytes), offset + max(0, end_token_length - 1))
    return source_bytes.count(b"\n", 0, offset) + 1


def _location_line(
    location: object,
    source_bytes: bytes,
    accepted_paths: frozenset[str],
    *,
    is_end: bool,
) -> int | None:
    if not isinstance(location, Mapping):
        return None
    # Macro expansion ranges can cross files or describe spelling rather than
    # the edited token.  They are intentionally rejected instead of guessed.
    if "spellingLoc" in location or "expansionLoc" in location or "includedFrom" in location:
        return None
    file_name = location.get("file")
    if file_name is not None and (
        not isinstance(file_name, str) or _normalized_path(file_name) not in accepted_paths
    ):
        return None
    line = location.get("line")
    if isinstance(line, int) and line >= 1:
        if not is_end:
            return line
        offset = location.get("offset")
        token_length = location.get("tokLen", 0)
        if isinstance(offset, int) and isinstance(token_length, int) and token_length > 1:
            return _offset_line(source_bytes, offset, end_token_length=token_length)
        return line
    offset = location.get("offset")
    if not isinstance(offset, int):
        return None
    token_length = location.get("tokLen", 0)
    return _offset_line(
        source_bytes,
        offset,
        end_token_length=token_length if is_end and isinstance(token_length, int) else 0,
    )


def extract_function_spans(
    ast: Mapping[str, Any],
    source: str,
    accepted_target_paths: Iterable[str],
) -> tuple[FunctionSpan, ...]:
    """Extract source-owned function definitions from Clang ``ast-dump=json``.

    Clang may omit ``line`` while retaining a byte ``offset``; line numbers are
    then derived from the exact UTF-8 source.  Explicit foreign-file, included,
    macro-expanded, implicit and lambda-call-operator nodes fail closed.
    """

    source_bytes = source.encode("utf-8")
    total_lines = max(1, len(source.splitlines()))
    accepted_paths = frozenset(_normalized_path(path) for path in accepted_target_paths)
    if not accepted_paths:
        raise ValueError("accepted_target_paths must not be empty")
    spans: set[FunctionSpan] = set()

    def visit(node: object, *, inside_lambda: bool = False) -> None:
        if not isinstance(node, Mapping):
            return
        kind = node.get("kind")
        now_inside_lambda = inside_lambda or kind == "LambdaExpr"
        children = node.get("inner", [])
        if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
            children = []
        if kind in FUNCTION_KINDS and not now_inside_lambda and node.get("isImplicit") is not True:
            has_body = any(
                isinstance(child, Mapping) and child.get("kind") == "CompoundStmt"
                for child in children
            )
            source_range = node.get("range")
            if has_body and isinstance(source_range, Mapping):
                begin = _location_line(
                    source_range.get("begin"), source_bytes, accepted_paths, is_end=False
                )
                end = _location_line(
                    source_range.get("end"), source_bytes, accepted_paths, is_end=True
                )
                node_location = node.get("loc")
                location_ok = True
                if isinstance(node_location, Mapping):
                    location_ok = (
                        _location_line(node_location, source_bytes, accepted_paths, is_end=False)
                        is not None
                    )
                if (
                    location_ok
                    and begin is not None
                    and end is not None
                    and 1 <= begin <= end <= total_lines
                ):
                    spans.add(
                        FunctionSpan(
                            start_line=begin,
                            end_line=end,
                            kind=str(kind),
                            name=str(node.get("name", "")),
                        )
                    )
        for child in children:
            visit(child, inside_lambda=now_inside_lambda)

    visit(ast)
    return tuple(sorted(spans))


def select_enclosing_function(
    spans: Iterable[FunctionSpan], anchors: Iterable[int]
) -> FunctionSpan | None:
    """Select the unique innermost definition containing all change anchors."""

    anchor_tuple = tuple(sorted(set(anchors)))
    if not anchor_tuple:
        return None
    candidates = [
        span
        for span in set(spans)
        if all(span.start_line <= line <= span.end_line for line in anchor_tuple)
    ]
    if not candidates:
        return None
    minimum_size = min(span.end_line - span.start_line for span in candidates)
    innermost = [span for span in candidates if span.end_line - span.start_line == minimum_size]
    return innermost[0] if len(innermost) == 1 else None


def select_file_window(
    total_lines: int,
    anchors: Iterable[int],
    spans: Iterable[FunctionSpan] = (),
    *,
    maximum_lines: int = 256,
    maximum_context_each_side: int = 96,
) -> FileWindow | None:
    """Build the maximum deterministic window around changed code.

    Every old-side function intersected by an anchor is retained in full.  If
    the resulting core cannot fit, the sample is rejected.  Remaining capacity
    is balanced around the core; an exact tie extends toward earlier lines.
    """

    if total_lines < 1 or maximum_lines < 1 or maximum_context_each_side < 0:
        raise ValueError("invalid window limits")
    anchor_tuple = tuple(sorted(set(anchors)))
    if not anchor_tuple or any(line < 1 or line > total_lines for line in anchor_tuple):
        return None
    core_start = min(anchor_tuple)
    core_end = max(anchor_tuple)
    for span in set(spans):
        if any(span.start_line <= line <= span.end_line for line in anchor_tuple):
            core_start = min(core_start, span.start_line)
            core_end = max(core_end, span.end_line)
    core_size = core_end - core_start + 1
    if core_size > maximum_lines:
        return None

    before_cap = min(maximum_context_each_side, core_start - 1)
    after_cap = min(maximum_context_each_side, total_lines - core_end)
    before = after = 0
    remaining = min(maximum_lines - core_size, before_cap + after_cap)
    while remaining:
        if before < before_cap and (before <= after or after >= after_cap):
            before += 1
        elif after < after_cap:
            after += 1
        else:
            break
        remaining -= 1
    return FileWindow(
        start_line=core_start - before,
        end_line=core_end + after,
        core_start_line=core_start,
        core_end_line=core_end,
        context_before=before,
        context_after=after,
    )
