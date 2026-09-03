"""RunBugRun-compatible output matching for A2 standalone programs.

The semantics mirror ``SubmissionOutputMatcher`` from RunBugRun's legacy
commit 5c023d6273ced705a5f83063b6b4cbf67aa81fa5, which corresponds to the
v0.0.1 data release used by this project.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re


UPSTREAM_REPOSITORY = "https://github.com/giganticode/run_bug_run"
UPSTREAM_COMMIT = "5c023d6273ced705a5f83063b6b4cbf67aa81fa5"
MATCHER_VERSION = "runbugrun-legacy-5c023d62"
DEFAULT_FLOAT_EPS = Decimal("1e-4")
FLOAT_EPS = {
    "p02400": "1e-5", "p02008": "1e-6", "p03882": "1e-9",
    "p02805": "1e-6", "p03585": "1e-9", "p03619": "1e-11",
    "p01562": "1e-6", "p03428": "1e-5", "p01837": "1e-6",
    "p03135": "1e-3", "p02764": "1e-6", "p03888": "1e-6",
    "p03110": "1e-5", "p03901": "1e-6", "p01836": "1e-8",
    "p00973": "1e-6", "p03043": "1e-9", "p01948": "1e-6",
    "p01800": "1e-6", "p03304": "1e-6", "p01704": "1e-4",
    "p03001": "1e-9", "p02072": "1e-3", "p02897": "1e-6",
    "p03754": "1e-6", "p02731": "1e-6", "p03879": "1e-9",
    "p02677": "1e-9", "p03953": "1e-9", "p02894": "1e-9",
    "p02705": "1e-2", "p01825": "1e-6", "p03514": "1e-9",
    "p01672": "1e-8", "p02882": "1e-6", "p03881": "1e-9",
    "p02075": "1e-9", "p00988": "1e-7", "p03744": "1e-6",
    "p01685": "1e-6", "p03872": "1e-9", "p01703": "1e-8",
    "p03869": "1e-9", "p02884": "1e-6", "p03866": "1e-9",
    "p02780": "1e-6", "p01568": "1e-6", "p01705": "1e-4",
    "p01576": "1e-8", "p02935": "1e-5", "p03004": "1e-9",
    "p02011": "1e-6", "p01708": "1e-2", "p03776": "1e-6",
    "p02934": "1e-5", "p01363": "1e-6", "p01510": "1e-9",
    "p03871": "1e-9", "p02379": "1e-4",
}
PROBLEM_FLOAT_EPS = {key: Decimal(value) for key, value in FLOAT_EPS.items()}
NUMBER_PREFIX = re.compile(r"-?\d+(?:\.\d+)?")
HORIZONTAL_WHITESPACE = " \t\r\f\v"


@dataclass(frozen=True)
class Number:
    value: Decimal


def _chomp(value: str) -> str:
    if value.endswith("\r\n"):
        return value[:-2]
    if value.endswith(("\n", "\r")):
        return value[:-1]
    return value


def _parse_line(line: str) -> list[str | Number]:
    result: list[str | Number] = []
    position = 0
    while position < len(line):
        while position < len(line) and line[position] in HORIZONTAL_WHITESPACE:
            position += 1
        if position == len(line):
            break
        number = NUMBER_PREFIX.match(line, position)
        if number is not None:
            result.append(Number(Decimal(number.group(0))))
            position = number.end()
            continue
        end = position
        while end < len(line) and not line[end].isspace():
            end += 1
        if end == position:
            raise ValueError(f"unsupported whitespace at output offset {position}")
        result.append(line[position:end])
        position = end
    return result


def parse_output(value: str) -> list[list[str | Number]]:
    """Parse while preserving line structure and ignoring horizontal spacing."""

    value = _chomp(value)
    if not value:
        return []
    return [_parse_line(line) for line in value.split("\n")]


def outputs_match(expected: str, actual: str | None, problem_id: str) -> bool:
    if actual is None:
        return False
    expected = _chomp(expected)
    actual = _chomp(actual)
    if expected == actual:
        return True
    try:
        expected_lines = parse_output(expected)
        actual_lines = parse_output(actual)
    except ValueError:
        return False
    if len(expected_lines) != len(actual_lines):
        return False
    epsilon = PROBLEM_FLOAT_EPS.get(problem_id, DEFAULT_FLOAT_EPS)
    for expected_line, actual_line in zip(expected_lines, actual_lines):
        if len(expected_line) != len(actual_line):
            return False
        for expected_item, actual_item in zip(expected_line, actual_line):
            if isinstance(expected_item, Number) and isinstance(actual_item, Number):
                if abs(actual_item.value - expected_item.value) > epsilon:
                    return False
            elif actual_item != expected_item:
                return False
    return True


def matcher_metadata() -> dict[str, str]:
    return {
        "name": "RunBugRun SubmissionOutputMatcher-compatible",
        "version": MATCHER_VERSION,
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_commit": UPSTREAM_COMMIT,
        "default_absolute_epsilon": str(DEFAULT_FLOAT_EPS),
    }
