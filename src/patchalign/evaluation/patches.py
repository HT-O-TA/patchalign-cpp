"""Strict parsing and policy checks for model-produced unified diffs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


class PatchParseError(ValueError):
    """The model text is not one complete, strict unified diff."""


class PatchPolicyError(ValueError):
    """A parsed patch violates the task's modification policy."""


_DIFF_HEADER = re.compile(r"^diff --git (a/[^\s]+) (b/[^\s]+)$")
_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(?: .*)?$")
_INDEX_HEADER = re.compile(r"^index [0-9a-fA-F]+\.\.[0-9a-fA-F]+(?: [0-7]{6})?$")
_BINARY_MARKERS = ("GIT binary patch", "Binary files ")
_FORBIDDEN_METADATA_PREFIXES = (
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
)


@dataclass(frozen=True)
class PatchedFile:
    old_path: str
    new_path: str
    hunk_count: int
    binary: bool = False
    forbidden_metadata: bool = False


@dataclass(frozen=True)
class ParsedPatch:
    files: tuple[PatchedFile, ...]


def _path_from_marker(line: str, marker: str) -> str:
    if not line.startswith(marker):
        raise PatchParseError(f"expected {marker.strip()} file marker")
    value = line[len(marker) :]
    path = value.split("\t", 1)[0]
    if not path or " " in path:
        raise PatchParseError("empty or whitespace-containing paths are not supported")
    return path


def _is_plain_file_header(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].startswith("--- ")
        and lines[index + 1].startswith("+++ ")
    )


def parse_unified_diff(raw_text: str) -> ParsedPatch:
    """Parse one pure unified diff without recovering text or fixing syntax."""

    if not raw_text or not raw_text.strip():
        raise PatchParseError("empty model output")
    if "\x00" in raw_text:
        raise PatchParseError("NUL bytes are not allowed")
    if "```" in raw_text:
        raise PatchParseError("Markdown fences are not allowed")

    lines = raw_text.splitlines()
    if not lines or not (lines[0].startswith("--- ") or lines[0].startswith("diff --git ")):
        raise PatchParseError("output must begin with a unified diff")

    files: list[PatchedFile] = []
    index = 0
    while index < len(lines):
        declared_old: str | None = None
        declared_new: str | None = None
        forbidden_metadata = False

        if lines[index].startswith("diff --git "):
            match = _DIFF_HEADER.fullmatch(lines[index])
            if match is None:
                raise PatchParseError("malformed git diff header")
            declared_old, declared_new = match.groups()
            index += 1

            while index < len(lines) and not lines[index].startswith("--- "):
                line = lines[index]
                if line.startswith(_BINARY_MARKERS):
                    files.append(
                        PatchedFile(
                            old_path=declared_old,
                            new_path=declared_new,
                            hunk_count=0,
                            binary=True,
                            forbidden_metadata=forbidden_metadata,
                        )
                    )
                    index += 1
                    while index < len(lines) and not lines[index].startswith("diff --git "):
                        index += 1
                    break
                if line.startswith(_FORBIDDEN_METADATA_PREFIXES):
                    forbidden_metadata = True
                    index += 1
                    continue
                if _INDEX_HEADER.fullmatch(line):
                    index += 1
                    continue
                raise PatchParseError(f"unsupported extended diff header: {line}")
            else:
                pass

            if files and files[-1].binary and files[-1].old_path == declared_old:
                continue
            if index >= len(lines):
                raise PatchParseError("missing file markers")

        old_path = _path_from_marker(lines[index], "--- ")
        index += 1
        if index >= len(lines):
            raise PatchParseError("missing new-file marker")
        new_path = _path_from_marker(lines[index], "+++ ")
        index += 1

        if declared_old is not None and (old_path != declared_old or new_path != declared_new):
            raise PatchParseError("git header and file markers disagree")

        hunk_count = 0
        while (
            index < len(lines)
            and not lines[index].startswith("diff --git ")
            and not _is_plain_file_header(lines, index)
        ):
            if not lines[index].startswith("@@ "):
                raise PatchParseError(f"expected hunk header, got: {lines[index]}")
            if _HUNK_HEADER.fullmatch(lines[index]) is None:
                raise PatchParseError("malformed hunk header")
            hunk_count += 1
            index += 1
            changed = False
            body_lines = 0
            while index < len(lines):
                line = lines[index]
                if (
                    line.startswith("diff --git ")
                    or line.startswith("@@ ")
                    or _is_plain_file_header(lines, index)
                ):
                    break
                if line == r"\ No newline at end of file":
                    if body_lines == 0:
                        raise PatchParseError("orphan no-newline marker")
                    index += 1
                    continue
                if not line or line[0] not in " +-":
                    raise PatchParseError(f"invalid hunk body line: {line}")
                if line[0] in "+-":
                    changed = True
                body_lines += 1
                index += 1
            if body_lines == 0 or not changed:
                raise PatchParseError("hunk must contain a change")

        if hunk_count == 0:
            raise PatchParseError("file patch has no hunks")
        files.append(
            PatchedFile(
                old_path=old_path,
                new_path=new_path,
                hunk_count=hunk_count,
                forbidden_metadata=forbidden_metadata,
            )
        )

    if not files:
        raise PatchParseError("patch has no files")
    return ParsedPatch(files=tuple(files))


def _validate_repo_path(prefixed_path: str, prefix: str) -> str:
    if not prefixed_path.startswith(prefix):
        raise PatchPolicyError(f"path must use {prefix} prefix")
    path = prefixed_path[len(prefix) :]
    pure_path = PurePosixPath(path)
    if not path or pure_path.is_absolute() or ".." in pure_path.parts or "\\" in path:
        raise PatchPolicyError("path must be a repository-relative POSIX path")
    return path


def enforce_patch_policy(parsed: ParsedPatch, allowed_paths: list[str]) -> tuple[str, ...]:
    """Enforce the first-version single-file and path policy."""

    if len(parsed.files) != 1:
        raise PatchPolicyError("first-version tasks allow exactly one modified file")

    patched_file = parsed.files[0]
    if patched_file.binary:
        raise PatchPolicyError("binary patches are forbidden")
    if patched_file.forbidden_metadata:
        raise PatchPolicyError("file creation, deletion, mode, rename, and copy metadata are forbidden")

    old_path = _validate_repo_path(patched_file.old_path, "a/")
    new_path = _validate_repo_path(patched_file.new_path, "b/")
    if old_path != new_path:
        raise PatchPolicyError("renames are forbidden")
    if old_path not in allowed_paths:
        raise PatchPolicyError("patch path is outside allowed_paths")
    return (old_path,)
