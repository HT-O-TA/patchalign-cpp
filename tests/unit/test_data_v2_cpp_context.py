from __future__ import annotations

from scripts.data.data_v2_cpp_context import (
    FileWindow,
    FunctionSpan,
    anchors_from_old_ranges,
    extract_function_spans,
    select_enclosing_function,
    select_file_window,
)


def location(offset: int, *, line: int | None = None, file: str | None = None) -> dict:
    value = {"offset": offset, "col": 1, "tokLen": 1}
    if line is not None:
        value["line"] = line
    if file is not None:
        value["file"] = file
    return value


def function_node(source: str, start: int, end: int, **updates: object) -> dict:
    lines = source.splitlines(keepends=True)
    start_offset = sum(len(line.encode("utf-8")) for line in lines[: start - 1])
    end_offset = sum(len(line.encode("utf-8")) for line in lines[: end - 1]) + len(
        lines[end - 1].encode("utf-8").rstrip(b"\r\n")
    ) - 1
    node = {
        "kind": "FunctionDecl",
        "name": "repair",
        "loc": location(start_offset),
        "range": {"begin": location(start_offset), "end": location(end_offset)},
        "inner": [{"kind": "CompoundStmt", "range": {}}],
    }
    node.update(updates)
    return node


def test_verified_old_ranges_cover_replacements_and_both_sides_of_insertions() -> None:
    assert anchors_from_old_ranges(3, [(2, 1)]) == (2,)
    assert anchors_from_old_ranges(2, [(1, 0)]) == (1, 2)
    assert anchors_from_old_ranges(0, [(0, 0)]) == (1,)


def test_ast_derives_missing_lines_from_utf8_byte_offsets() -> None:
    source = "// π\nint repair() {\n  return 1;\n}\n"
    ast = {"kind": "TranslationUnitDecl", "inner": [function_node(source, 2, 4)]}
    assert extract_function_spans(ast, source, ["src/main.cpp"]) == (
        FunctionSpan(2, 4, "FunctionDecl", "repair"),
    )


def test_ast_accepts_nested_method_but_excludes_lambda_and_implicit_nodes() -> None:
    source = "namespace n {\nstruct C {\n  int f() {\n    return 1;\n  }\n};\n}\n"
    method = function_node(source, 3, 5, kind="CXXMethodDecl", name="f")
    implicit = function_node(source, 3, 5, kind="CXXMethodDecl", name="implicit", isImplicit=True)
    lambda_call = function_node(source, 3, 5, kind="CXXMethodDecl", name="operator()")
    ast = {
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "NamespaceDecl",
                "inner": [{"kind": "CXXRecordDecl", "inner": [method, implicit]}],
            },
            {"kind": "LambdaExpr", "inner": [lambda_call]},
        ],
    }
    assert extract_function_spans(ast, source, ["src/main.cpp"]) == (
        FunctionSpan(3, 5, "CXXMethodDecl", "f"),
    )


def test_ast_rejects_foreign_included_and_macro_locations() -> None:
    source = "int f() {\n  return 1;\n}\n"
    foreign = function_node(source, 1, 3)
    foreign["range"]["begin"]["file"] = "include/other.hpp"
    included = function_node(source, 1, 3)
    included["loc"]["includedFrom"] = {"file": "src/main.cpp"}
    macro = function_node(source, 1, 3)
    macro["range"]["begin"] = {"spellingLoc": location(0), "expansionLoc": location(0)}
    ast = {"kind": "TranslationUnitDecl", "inner": [foreign, included, macro]}
    assert extract_function_spans(ast, source, ["src/main.cpp"]) == ()


def test_unique_innermost_function_is_selected_and_cross_function_change_falls_back() -> None:
    outer = FunctionSpan(1, 20, "FunctionDecl", "outer")
    inner = FunctionSpan(5, 10, "CXXMethodDecl", "inner")
    other = FunctionSpan(30, 40, "FunctionDecl", "other")
    assert select_enclosing_function([outer, inner, other], [6, 8]) == inner
    assert select_enclosing_function([outer, inner, other], [8, 32]) is None


def test_file_window_preserves_intersected_functions_and_balances_context() -> None:
    spans = [
        FunctionSpan(100, 119, "FunctionDecl", "left"),
        FunctionSpan(130, 149, "FunctionDecl", "right"),
    ]
    window = select_file_window(400, [110, 140], spans)
    assert window == FileWindow(
        start_line=4,
        end_line=245,
        core_start_line=100,
        core_end_line=149,
        context_before=96,
        context_after=96,
    )
    assert window.end_line - window.start_line + 1 == 242
    assert window.context_before <= 96 and window.context_after <= 96


def test_file_window_rejects_oversized_core_and_reallocates_at_boundary() -> None:
    assert select_file_window(400, [10, 300]) is None
    window = select_file_window(300, [2, 3])
    assert window is not None
    assert window.start_line == 1
    assert window.context_before == 1
    assert window.context_after == 96
