from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "a2-execution-v0.1.schema.json"
FIXTURE = ROOT / "tests" / "fixtures" / "a2" / "a2-execution.valid.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def validator() -> Draft202012Validator:
    schema = load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_a2_execution_schema_accepts_explicit_not_applicable_sanitizer() -> None:
    validator().validate(load(FIXTURE))


def test_a2_execution_schema_accepts_test_outcome() -> None:
    record = copy.deepcopy(load(FIXTURE))
    fixed = record["versions"]["fixed"]  # type: ignore[index]
    outcome = {**fixed["compile"], "test_id": "case-1", "matched": True}
    fixed["suites"] = {"regression": [outcome]}
    fixed["summary"] = {"regression": {"total": 1, "matched": 1, "all_matched": True}}
    validator().validate(record)


def test_a2_execution_schema_rejects_missing_sanitizer_applicability() -> None:
    record = copy.deepcopy(load(FIXTURE))
    del record["sanitizer"]["sanitizer_applicable"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        validator().validate(record)


def test_a2_execution_schema_requires_controlled_sanitizer_metadata() -> None:
    record = copy.deepcopy(load(FIXTURE))
    record["sanitizer"] = {"sanitizer_applicable": True, "status": "not_run"}
    with pytest.raises(ValidationError):
        validator().validate(record)
