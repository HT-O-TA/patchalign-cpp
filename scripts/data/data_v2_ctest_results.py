"""Canonicalize CTest identities and structured results for Data-v2 replay."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


MAX_TESTS = 10_000
MAX_STRUCTURED_BYTES = 16 * 1024 * 1024


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def _normalize_string(value: str, roots: Mapping[str, str]) -> str:
    normalized = value.replace("\\", "/")
    ordered = sorted(
        ((str(PurePosixPath(root.replace("\\", "/"))), token) for root, token in roots.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for root, token in ordered:
        if normalized == root:
            normalized = token
        else:
            normalized = normalized.replace(root + "/", token.rstrip("/") + "/")
    return normalized


def _normalize_value(value: object, roots: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return _normalize_string(value, roots)
    if isinstance(value, list):
        return [_normalize_value(item, roots) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_value(item, roots)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise ValueError(f"unsupported CTest value type: {type(value).__name__}")


@dataclass(frozen=True)
class TestIdentity:
    name: str
    test_id: str
    command: tuple[str, ...]
    properties: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class TestResult:
    name: str
    test_id: str
    status: str
    completion_status: str
    exit_code: str | None
    output_sha256: str
    result_sha256: str


def parse_ctest_catalog(
    payload: bytes,
    roots: Mapping[str, str],
    *,
    maximum_tests: int = MAX_TESTS,
) -> tuple[TestIdentity, ...]:
    """Parse and canonicalize ``ctest --show-only=json-v1`` output."""

    if len(payload) > MAX_STRUCTURED_BYTES:
        raise ValueError("ctest enumeration exceeds byte limit")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid CTest enumeration JSON") from error
    if not isinstance(document, Mapping) or document.get("kind") != "ctestInfo":
        raise ValueError("unexpected CTest enumeration kind")
    version = document.get("version")
    if not isinstance(version, Mapping) or version.get("major") != 1:
        raise ValueError("unsupported CTest enumeration version")
    tests = document.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("CTest registered no tests")
    if len(tests) > maximum_tests:
        raise ValueError("CTest test count exceeds limit")

    identities: list[TestIdentity] = []
    names: set[str] = set()
    ids: set[str] = set()
    for test in tests:
        if not isinstance(test, Mapping):
            raise ValueError("invalid CTest test entry")
        name = test.get("name")
        command = test.get("command")
        properties = test.get("properties", [])
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("CTest test names must be non-empty and unique")
        if (
            not isinstance(command, Sequence)
            or isinstance(command, (str, bytes))
            or not command
            or not all(isinstance(item, str) for item in command)
        ):
            raise ValueError(f"invalid command for CTest test {name}")
        if not isinstance(properties, list):
            raise ValueError(f"invalid properties for CTest test {name}")
        normalized_properties: list[tuple[str, object]] = []
        property_names: set[str] = set()
        for prop in properties:
            if not isinstance(prop, Mapping) or set(prop) != {"name", "value"}:
                raise ValueError(f"invalid property for CTest test {name}")
            prop_name = prop.get("name")
            if not isinstance(prop_name, str) or not prop_name or prop_name in property_names:
                raise ValueError(f"duplicate/invalid property for CTest test {name}")
            property_names.add(prop_name)
            normalized_properties.append(
                (prop_name, _normalize_value(prop.get("value"), roots))
            )
        normalized_command = tuple(_normalize_string(item, roots) for item in command)
        normalized_properties.sort(key=lambda item: item[0])
        identity_payload = {
            "name": name,
            "command": normalized_command,
            "properties": normalized_properties,
        }
        test_id = sha256(identity_payload)
        if test_id in ids:
            raise ValueError("CTest produced duplicate canonical test identities")
        names.add(name)
        ids.add(test_id)
        identities.append(
            TestIdentity(name, test_id, normalized_command, tuple(normalized_properties))
        )
    return tuple(sorted(identities, key=lambda item: (item.test_id, item.name)))


def _measurement_map(test: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for measurement in test.findall("./Results/NamedMeasurement"):
        name = measurement.get("name")
        value_node = measurement.find("Value")
        if not name or name in values or value_node is None:
            raise ValueError("invalid/duplicate CTest named measurement")
        values[name] = value_node.text or ""
    return values


def parse_ctest_results(
    payload: bytes,
    catalog: Sequence[TestIdentity],
    roots: Mapping[str, str],
) -> tuple[TestResult, ...]:
    """Parse uncompressed CTest dashboard ``Test.xml`` into stable results."""

    if len(payload) > MAX_STRUCTURED_BYTES:
        raise ValueError("CTest Test.xml exceeds byte limit")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ValueError("invalid CTest Test.xml") from error
    testing = root.find("Testing") if root.tag == "Site" else None
    if testing is None:
        raise ValueError("unexpected CTest Test.xml root")
    by_name = {item.name: item for item in catalog}
    if len(by_name) != len(catalog) or not by_name:
        raise ValueError("invalid empty/duplicate catalog")

    result_nodes = testing.findall("Test")
    result_names = [node.findtext("Name") for node in result_nodes]
    if any(not isinstance(name, str) or not name for name in result_names):
        raise ValueError("CTest result has missing test name")
    if len(set(result_names)) != len(result_names):
        raise ValueError("CTest result has duplicate test name")
    if set(result_names) != set(by_name):
        raise ValueError("CTest result/catalog test sets differ")

    results: list[TestResult] = []
    for node, name in zip(result_nodes, result_names, strict=True):
        assert isinstance(name, str)
        identity = by_name[name]
        raw_status = (node.get("Status") or "").casefold()
        measurements = _measurement_map(node)
        completion = measurements.get("Completion Status", "")
        exit_code = measurements.get("Exit Code")
        completion_folded = completion.casefold()
        if "timeout" in completion_folded or (exit_code and "timeout" in exit_code.casefold()):
            status = "timeout"
        elif raw_status == "passed" and completion == "Completed":
            status = "pass"
        elif raw_status == "failed":
            status = "fail"
        else:
            status = "infrastructure_error"

        output_nodes = node.findall("./Results/Measurement/Value")
        if len(output_nodes) != 1 or output_nodes[0].attrib:
            raise ValueError(f"missing or encoded CTest output for {name}")
        normalized_output = _normalize_string(output_nodes[0].text or "", roots)
        output_sha = "sha256:" + hashlib.sha256(normalized_output.encode("utf-8")).hexdigest()
        result_payload = {
            "test_id": identity.test_id,
            "status": status,
            "completion_status": completion,
            "exit_code": exit_code,
            "output_sha256": output_sha,
        }
        results.append(
            TestResult(
                name=name,
                test_id=identity.test_id,
                status=status,
                completion_status=completion,
                exit_code=exit_code,
                output_sha256=output_sha,
                result_sha256=sha256(result_payload),
            )
        )
    return tuple(sorted(results, key=lambda item: (item.test_id, item.name)))
