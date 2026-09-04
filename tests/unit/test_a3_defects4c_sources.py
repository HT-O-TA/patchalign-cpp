from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from scripts.external.prepare_defects4c_sources import validate_config

ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    return json.loads((ROOT / "configs/external/a3_defects4c_sources_v1.json").read_text(encoding="utf-8"))


def test_defects4c_source_contract_is_frozen() -> None:
    value = config()
    validate_config(value)
    assert value["selection"]["expected_unique_pairs"] == 206
    assert value["selection"]["prompt_sha256"] == "sha256:3ef1b7e0867b8616f6becf48c30c92478a04a3111dba5f6398c2887db87808ff"
    assert value["download"]["workers"] == 4


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("official_source", "git_commit"), "0" * 40),
        (("selection", "expected_projects"), 12),
        (("selection", "expected_unique_pairs"), 205),
        (("download", "workers"), 16),
        (("download", "fetch_timeout_seconds"), 60),
    ],
)
def test_defects4c_source_contract_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
