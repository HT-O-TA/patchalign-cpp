from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from scripts.external.qualify_defects4c_case import validate_config

ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    return json.loads((ROOT / "configs/external/a3_defects4c_qualification_v1.json").read_text(encoding="utf-8"))


def test_defects4c_qualification_contract_is_frozen() -> None:
    value = config()
    validate_config(value)
    assert value["source"]["record_count"] == 203
    assert value["qualification"]["minimum_qualified"] == 150
    assert value["qualification"]["network"] == "unshared"
    assert value["qualification"]["cleanup_build_directory"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("source", "plan_sha256"), "sha256:" + "0" * 64),
        (("source", "record_count"), 202),
        (("runtime", "rootfs_archive_sha256"), "sha256:" + "0" * 64),
        (("runtime", "bwrap_sha256"), "sha256:" + "0" * 64),
        (("qualification", "minimum_qualified"), 149),
        (("qualification", "network"), "shared"),
        (("qualification", "cleanup_build_directory"), False),
    ],
)
def test_defects4c_qualification_rejects_drift(path: tuple[str, ...], value: object) -> None:
    changed = copy.deepcopy(config())
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_config(changed)
