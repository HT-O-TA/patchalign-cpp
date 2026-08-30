from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "a0"


CASES = (
    ("sample-v0.1.schema.json", "sample.valid.json"),
    ("prediction-v0.1.schema.json", "prediction.valid.json"),
    ("run-manifest-v0.1.schema.json", "run-manifest.valid.json"),
)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("schema_name", "fixture_name"), CASES)
def test_schema_and_positive_fixture(schema_name: str, fixture_name: str) -> None:
    schema = load_json(SCHEMA_DIR / schema_name)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(
        load_json(FIXTURE_DIR / fixture_name)
    )


def test_sample_rejects_parent_path_escape() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.1.schema.json")
    sample = copy.deepcopy(load_json(FIXTURE_DIR / "sample.valid.json"))
    sample["allowed_paths"] = ["../tests/test_add.cpp"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_sample_rejects_unknown_fields() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.1.schema.json")
    sample = copy.deepcopy(load_json(FIXTURE_DIR / "sample.valid.json"))
    sample["untracked_note"] = "must not silently enter the canonical record"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_prediction_rejects_non_hash_config_identifier() -> None:
    schema = load_json(SCHEMA_DIR / "prediction-v0.1.schema.json")
    prediction = copy.deepcopy(load_json(FIXTURE_DIR / "prediction.valid.json"))
    prediction["model"]["config_sha256"] = "latest"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(prediction)
