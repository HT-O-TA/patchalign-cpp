from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "a2-execution-v0.2.schema.json"
FIXTURE = ROOT / "tests" / "fixtures" / "a2" / "a2-execution-v0.2.valid.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def validator() -> Draft202012Validator:
    schema = load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_a2_execution_v02_accepts_matcher_provenance() -> None:
    validator().validate(load(FIXTURE))


def test_a2_execution_v02_rejects_unpinned_matcher() -> None:
    record = copy.deepcopy(load(FIXTURE))
    record["output_matcher"]["upstream_commit"] = "main"  # type: ignore[index]
    with pytest.raises(ValidationError):
        validator().validate(record)


def test_a2_execution_v02_requires_partition_acceptance() -> None:
    record = copy.deepcopy(load(FIXTURE))
    del record["acceptance"]["partition_contract_satisfied"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        validator().validate(record)
