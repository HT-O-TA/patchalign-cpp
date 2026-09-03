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
    ("run-manifest-v0.2.schema.json", "run-manifest-v0.2.valid.json"),
    ("sample-v0.2.schema.json", "sample-v0.2.function-single-line.valid.json"),
    ("sample-v0.2.schema.json", "sample-v0.2.function-multi-line.valid.json"),
    ("sample-v0.2.schema.json", "sample-v0.2.file-window-add-helper.valid.json"),
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


def load_v02_sample(fixture_name: str = "sample-v0.2.function-single-line.valid.json") -> dict[str, object]:
    return copy.deepcopy(load_json(FIXTURE_DIR / fixture_name))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("changed_logical_lines", 2),
        ("input_token_count", 4097),
        ("hidden_test_count", 0),
        ("regression_test_count", 2),
        ("public_test_command", None),
        ("hidden_test_command", None),
        ("regression_test_command", None),
    ),
)
def test_v02_rejects_invalid_internal_function_sample(field: str, value: object) -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample()
    sample[field] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("file_window_lines", 257),
        ("file_window_context_before", 97),
        ("file_window_context_after", 97),
        ("changed_logical_lines", 41),
    ),
)
def test_v02_rejects_file_window_limit_violations(field: str, value: object) -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample("sample-v0.2.file-window-add-helper.valid.json")
    sample[field] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_v02_rejects_window_values_for_function_task() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample()
    sample["file_window_lines"] = 20
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_v02_rejects_missing_frozen_field() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample()
    del sample["edit_type"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_v02_rejects_multiple_allowed_paths() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample()
    sample["allowed_paths"] = ["src/add.cpp", "include/add.hpp"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_v02_rejects_parent_path_escape() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample()
    sample["allowed_paths"] = ["../tests/test_add.cpp"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_v02_rejects_unknown_fields() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample()
    sample["untracked_note"] = "must not silently enter the canonical record"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


@pytest.mark.parametrize(
    ("fixture_name", "changed_logical_lines"),
    (
        ("sample-v0.2.function-multi-line.valid.json", 1),
        ("sample-v0.2.function-multi-line.valid.json", 21),
        ("sample-v0.2.file-window-add-helper.valid.json", 1),
    ),
)
def test_v02_rejects_edit_type_line_count_mismatch(
    fixture_name: str, changed_logical_lines: int
) -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample(fixture_name)
    sample["changed_logical_lines"] = changed_logical_lines
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_v02_rejects_wrong_schema_version() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.2.schema.json")
    sample = load_v02_sample()
    sample["schema_version"] = "0.1.0"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)


def test_v01_rejects_v02_fields() -> None:
    schema = load_json(SCHEMA_DIR / "sample-v0.1.schema.json")
    sample = copy.deepcopy(load_json(FIXTURE_DIR / "sample.valid.json"))
    sample["edit_type"] = "single_line"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(sample)
