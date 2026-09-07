"""Build a deterministic, non-shell Clang AST argv from compile_commands.json."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Sequence


MAX_COMPILE_DATABASE_BYTES = 16 * 1024 * 1024

_COMPILER_RE = re.compile(
    r"^(?:[a-z0-9_.+-]+-)?(?:c\+\+|g\+\+|clang\+\+|gcc|clang)(?:-[0-9.]+)?$",
    re.IGNORECASE,
)
_LAUNCHERS = frozenset({"ccache", "sccache"})
_DROP_EXACT = frozenset(
    {
        "-c",
        "-S",
        "-E",
        "-M",
        "-MM",
        "-MD",
        "-MMD",
        "-MP",
        "-MG",
        "-pipe",
        "-fsyntax-only",
    }
)
_DROP_WITH_VALUE = frozenset(
    {"-o", "-MF", "-MT", "-MQ", "-MJ", "--serialize-diagnostics", "-dependency-file"}
)
_DROP_PREFIXES = (
    "-MF",
    "-MT",
    "-MQ",
    "-MJ",
    "-Wp,-M",
    "--serialize-diagnostics=",
    "-dependency-file=",
    "-Werror",
)
_DANGEROUS_EXACT = frozenset(
    {
        "--",
        "-Xclang",
        "-cc1",
        "-load",
        "-plugin",
        "-add-plugin",
        "-mllvm",
        "-wrapper",
        "-B",
        "--config",
        "-save-temps",
        "-ftime-trace",
    }
)
_DANGEROUS_PREFIXES = (
    "@",
    "-B",
    "-fplugin",
    "-fpass-plugin",
    "--config=",
    "-specs=",
    "-save-temps=",
    "-ftime-trace=",
    "-march=native",
    "-mtune=native",
    "-mcpu=native",
)
_SHELL_META = re.compile(r"[|;&<>`]|\$\(|\$\{")


@dataclass(frozen=True)
class AstInvocation:
    directory: str
    source_file: str
    argv: tuple[str, ...]
    canonical_sha256: str


def _absolute(path: str, base: str | None = None) -> str:
    if not path or "\x00" in path or "\n" in path or "\r" in path:
        raise ValueError("invalid path")
    value = path.replace("\\", "/")
    if not posixpath.isabs(value):
        if base is None:
            raise ValueError("relative path has no base")
        value = posixpath.join(base, value)
    return posixpath.normpath(value)


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _normalize(value: str, roots: Mapping[str, str]) -> str:
    normalized = value.replace("\\", "/")
    for root, token in sorted(roots.items(), key=lambda item: len(item[0]), reverse=True):
        canonical_root = str(PurePosixPath(root.replace("\\", "/")))
        if normalized == canonical_root:
            normalized = token
            continue
        normalized = normalized.replace(
            canonical_root.rstrip("/") + "/", token.rstrip("/") + "/"
        )
        if normalized.endswith(canonical_root):
            normalized = normalized[: -len(canonical_root)] + token
    return normalized


def _entry_argv(entry: Mapping[str, object]) -> list[str]:
    has_arguments = "arguments" in entry
    has_command = "command" in entry
    if has_arguments == has_command:
        raise ValueError("compile entry must contain exactly one of arguments/command")
    if has_arguments:
        arguments = entry.get("arguments")
        if (
            not isinstance(arguments, Sequence)
            or isinstance(arguments, (str, bytes))
            or not arguments
            or not all(isinstance(item, str) and item for item in arguments)
        ):
            raise ValueError("invalid compile arguments")
        return list(arguments)
    command = entry.get("command")
    if not isinstance(command, str) or not command:
        raise ValueError("invalid compile command")
    try:
        arguments = shlex.split(command, posix=True)
    except ValueError as error:
        raise ValueError("invalid compile command quoting") from error
    if not arguments:
        raise ValueError("empty compile command")
    return arguments


def _compiler_index(arguments: Sequence[str]) -> int:
    first = posixpath.basename(arguments[0])
    index = 1 if first in _LAUNCHERS else 0
    if index >= len(arguments) or not _COMPILER_RE.fullmatch(
        posixpath.basename(arguments[index])
    ):
        raise ValueError("unsupported compiler/launcher")
    return index


def _sanitize_arguments(
    arguments: Sequence[str], directory: str, source_file: str, frozen_clang: str
) -> tuple[str, ...]:
    compiler_index = _compiler_index(arguments)
    kept: list[str] = []
    source_occurrences = 0
    index = compiler_index + 1
    while index < len(arguments):
        token = arguments[index]
        if not token or "\x00" in token or "\n" in token or "\r" in token:
            raise ValueError("invalid compile argument")
        if _SHELL_META.search(token):
            raise ValueError("shell metacharacter in compile argument")
        if token.startswith("-o") and token != "-o":
            raise ValueError("unsafe/unsupported attached output argument")
        if token in _DANGEROUS_EXACT or token.startswith(_DANGEROUS_PREFIXES):
            raise ValueError(f"unsafe/nondeterministic compile argument: {token}")
        if token in _DROP_WITH_VALUE:
            if index + 1 >= len(arguments):
                raise ValueError(f"compile argument {token} has no value")
            index += 2
            continue
        if token in _DROP_EXACT or token.startswith(_DROP_PREFIXES):
            index += 1
            continue
        if not token.startswith("-"):
            try:
                candidate = _absolute(token, directory)
            except ValueError:
                candidate = ""
            if candidate == source_file:
                source_occurrences += 1
                index += 1
                continue
        kept.append(token)
        index += 1
    if source_occurrences != 1:
        raise ValueError("compile command must reference target source exactly once")
    return (
        frozen_clang,
        *kept,
        "-fsyntax-only",
        "-Xclang",
        "-ast-dump=json",
        source_file,
    )


def build_ast_invocation(
    payload: bytes,
    *,
    target_source: str,
    checkout_root: str,
    build_root: str,
    frozen_clang: str,
) -> AstInvocation:
    """Select one target TU and produce an argv that is never evaluated by a shell."""

    if len(payload) > MAX_COMPILE_DATABASE_BYTES:
        raise ValueError("compile database exceeds byte limit")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid compile database JSON") from error
    if not isinstance(document, list) or not document:
        raise ValueError("compile database must be a non-empty list")

    checkout = _absolute(checkout_root)
    build = _absolute(build_root)
    source = _absolute(target_source, checkout)
    clang = _absolute(frozen_clang)
    if not _within(source, checkout):
        raise ValueError("target source escapes checkout")

    matches: list[tuple[Mapping[str, object], str]] = []
    for raw_entry in document:
        if not isinstance(raw_entry, Mapping):
            raise ValueError("invalid compile database entry")
        directory_value = raw_entry.get("directory")
        file_value = raw_entry.get("file")
        if not isinstance(directory_value, str) or not isinstance(file_value, str):
            raise ValueError("compile entry lacks directory/file")
        directory = _absolute(directory_value)
        if not (_within(directory, checkout) or _within(directory, build)):
            raise ValueError("compile directory escapes checkout/build root")
        entry_source = _absolute(file_value, directory)
        if not _within(entry_source, checkout):
            raise ValueError("compile source escapes checkout")
        if entry_source == source:
            matches.append((raw_entry, directory))
    if len(matches) != 1:
        raise ValueError("target source must have exactly one compile entry")

    entry, directory = matches[0]
    argv = _sanitize_arguments(_entry_argv(entry), directory, source, clang)
    roots = {build: "$BUILD", checkout: "$CHECKOUT"}
    canonical_payload = {
        "directory": _normalize(directory, roots),
        "source_file": _normalize(source, roots),
        "argv": [_normalize(item, roots) for item in argv],
    }
    invocation_sha = "sha256:" + hashlib.sha256(
        json.dumps(
            canonical_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return AstInvocation(directory, source, argv, invocation_sha)
