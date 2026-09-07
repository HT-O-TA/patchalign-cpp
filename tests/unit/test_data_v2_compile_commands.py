from __future__ import annotations

import json

import pytest

from scripts.data.data_v2_compile_commands import build_ast_invocation


def encode(entry: dict | list[dict]) -> bytes:
    return json.dumps(entry if isinstance(entry, list) else [entry]).encode()


def test_arguments_form_strips_side_effects_and_replaces_launcher_compiler() -> None:
    invocation = build_ast_invocation(
        encode(
            {
                "directory": "/work/build",
                "file": "/work/src/lib/fix.cpp",
                "arguments": [
                    "ccache",
                    "/usr/bin/g++-12",
                    "-I",
                    "/work/src/include",
                    "-DVALUE=1",
                    "-Werror=unused-variable",
                    "-MMD",
                    "-MF",
                    "obj/fix.d",
                    "-MTobj/fix.o",
                    "-c",
                    "/work/src/lib/fix.cpp",
                    "-o",
                    "obj/fix.o",
                ],
            }
        ),
        target_source="lib/fix.cpp",
        checkout_root="/work/src",
        build_root="/work/build",
        frozen_clang="/usr/bin/clang++-16",
    )
    assert invocation.argv == (
        "/usr/bin/clang++-16",
        "-I",
        "/work/src/include",
        "-DVALUE=1",
        "-fsyntax-only",
        "-Xclang",
        "-ast-dump=json",
        "/work/src/lib/fix.cpp",
    )


def test_command_form_has_run_independent_canonical_hash() -> None:
    def build(run: str) -> str:
        return build_ast_invocation(
            encode(
                {
                    "directory": f"/{run}/build",
                    "file": f"/{run}/src/main.cpp",
                    "command": (
                        f'/usr/bin/c++ -I "../src/include dir" '
                        f'-DROOT=/{run}/src/config -c ../src/main.cpp -o main.o'
                    ),
                }
            ),
            target_source="main.cpp",
            checkout_root=f"/{run}/src",
            build_root=f"/{run}/build",
            frozen_clang="/usr/bin/clang++-16",
        ).canonical_sha256

    assert build("run-one") == build("run-two")


def test_rejects_shell_plugins_response_files_and_native_cpu_flags() -> None:
    unsafe_tokens = [
        "&&",
        "$(touch-bad)",
        "@flags.rsp",
        "-Xclang",
        "-fplugin=bad.so",
        "--config=bad.cfg",
        "-march=native",
        "-obad.o",
        "-Btoolchain",
    ]
    for token in unsafe_tokens:
        entry = {
            "directory": "/work/build",
            "file": "/work/src/main.cpp",
            "arguments": ["c++", token, "/work/src/main.cpp", "-c"],
        }
        with pytest.raises(ValueError, match="unsafe|shell"):
            build_ast_invocation(
                encode(entry),
                target_source="main.cpp",
                checkout_root="/work/src",
                build_root="/work/build",
                frozen_clang="/usr/bin/clang++-16",
            )


def test_rejects_ambiguous_target_and_paths_outside_roots() -> None:
    entry = {
        "directory": "/work/build",
        "file": "/work/src/main.cpp",
        "arguments": ["c++", "/work/src/main.cpp", "-c"],
    }
    with pytest.raises(ValueError, match="exactly one"):
        build_ast_invocation(
            encode([entry, entry]),
            target_source="main.cpp",
            checkout_root="/work/src",
            build_root="/work/build",
            frozen_clang="/usr/bin/clang++-16",
        )
    outside = {**entry, "directory": "/outside"}
    with pytest.raises(ValueError, match="escapes"):
        build_ast_invocation(
            encode(outside),
            target_source="main.cpp",
            checkout_root="/work/src",
            build_root="/work/build",
            frozen_clang="/usr/bin/clang++-16",
        )
