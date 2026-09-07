from __future__ import annotations

import json

import pytest

from scripts.data.data_v2_ctest_results import (
    parse_ctest_catalog,
    parse_ctest_results,
)


ROOTS = {"/tmp/work/fixed": "$CHECKOUT", "/tmp/work/fixed/build": "$BUILD"}


def catalog_payload(order: tuple[str, ...] = ("pass.case", "fail[case]", "slow")) -> bytes:
    tests = {
        "pass.case": {
            "name": "pass.case",
            "command": ["/tmp/work/fixed/build/bin/tester", "--pass"],
            "properties": [
                {"name": "WORKING_DIRECTORY", "value": "/tmp/work/fixed/build"},
                {"name": "LABELS", "value": ["unit", "stable"]},
            ],
        },
        "fail[case]": {
            "name": "fail[case]",
            "command": ["/tmp/work/fixed/build/bin/tester", "--fail"],
            "properties": [],
        },
        "slow": {
            "name": "slow",
            "command": ["/tmp/work/fixed/build/bin/tester", "--slow"],
            "properties": [{"name": "TIMEOUT", "value": 1.0}],
        },
    }
    return json.dumps(
        {
            "kind": "ctestInfo",
            "version": {"major": 1, "minor": 0},
            "tests": [tests[name] for name in order],
        }
    ).encode()


def test_catalog_is_order_independent_and_normalizes_ephemeral_roots() -> None:
    first = parse_ctest_catalog(catalog_payload(), ROOTS)
    second = parse_ctest_catalog(catalog_payload(("slow", "fail[case]", "pass.case")), ROOTS)
    assert first == second
    passing = next(item for item in first if item.name == "pass.case")
    assert passing.command[0] == "$BUILD/bin/tester"
    assert dict(passing.properties)["WORKING_DIRECTORY"] == "$BUILD"


def test_catalog_rejects_duplicates_empty_and_oversized_sets() -> None:
    duplicate = json.loads(catalog_payload())
    duplicate["tests"].append(duplicate["tests"][0])
    with pytest.raises(ValueError, match="unique"):
        parse_ctest_catalog(json.dumps(duplicate).encode(), ROOTS)
    empty = {"kind": "ctestInfo", "version": {"major": 1}, "tests": []}
    with pytest.raises(ValueError, match="registered no tests"):
        parse_ctest_catalog(json.dumps(empty).encode(), ROOTS)
    with pytest.raises(ValueError, match="count exceeds"):
        parse_ctest_catalog(catalog_payload(), ROOTS, maximum_tests=2)


def test_structured_results_classify_pass_fail_timeout_and_normalize_output() -> None:
    catalog = parse_ctest_catalog(catalog_payload(), ROOTS)
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Site><Testing><TestList><Test>./pass.case</Test><Test>./fail[case]</Test>
<Test>./slow</Test></TestList>
<Test Status="passed"><Name>pass.case</Name><Results>
<NamedMeasurement name="Execution Time"><Value>9.9</Value></NamedMeasurement>
<NamedMeasurement name="Completion Status"><Value>Completed</Value></NamedMeasurement>
<Measurement><Value>ok /tmp/work/fixed/result</Value></Measurement></Results></Test>
<Test Status="failed"><Name>fail[case]</Name><Results>
<NamedMeasurement name="Exit Code"><Value>SEGFAULT</Value></NamedMeasurement>
<NamedMeasurement name="Completion Status"><Value>SEGFAULT</Value></NamedMeasurement>
<Measurement><Value>wrong</Value></Measurement></Results></Test>
<Test Status="failed"><Name>slow</Name><Results>
<NamedMeasurement name="Exit Code"><Value>Timeout</Value></NamedMeasurement>
<NamedMeasurement name="Completion Status"><Value>Timeout</Value></NamedMeasurement>
<Measurement><Value>partial</Value></Measurement></Results></Test>
</Testing></Site>'''
    results = parse_ctest_results(xml, catalog, ROOTS)
    assert {item.name: item.status for item in results} == {
        "pass.case": "pass",
        "fail[case]": "fail",
        "slow": "timeout",
    }
    passing = next(item for item in results if item.name == "pass.case")
    failing = next(item for item in results if item.name == "fail[case]")
    assert passing.output_sha256 != failing.output_sha256


def test_results_reject_set_drift_and_encoded_output() -> None:
    catalog = parse_ctest_catalog(catalog_payload(("pass.case",)), ROOTS)
    missing = b"<Site><Testing></Testing></Site>"
    with pytest.raises(ValueError, match="sets differ"):
        parse_ctest_results(missing, catalog, ROOTS)
    encoded = b'''<Site><Testing><Test Status="passed"><Name>pass.case</Name><Results>
<NamedMeasurement name="Completion Status"><Value>Completed</Value></NamedMeasurement>
<Measurement><Value encoding="base64">eA==</Value></Measurement></Results></Test>
</Testing></Site>'''
    with pytest.raises(ValueError, match="encoded"):
        parse_ctest_results(encoded, catalog, ROOTS)
