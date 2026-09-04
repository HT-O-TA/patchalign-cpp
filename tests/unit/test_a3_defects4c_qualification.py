from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from scripts.external.qualify_defects4c_case import validate_config
from scripts.external.aggregate_defects4c_qualification import adapted_prompt

ROOT = Path(__file__).resolve().parents[2]


def config() -> dict:
    return json.loads((ROOT / "configs/external/a3_defects4c_qualification_v1.json").read_text(encoding="utf-8"))


def test_defects4c_qualification_contract_is_frozen() -> None:
    value = config()
    validate_config(value)
    assert value["source"]["record_count"] == 203
    assert value["qualification"]["minimum_qualified"] == 150
    assert value["prompt"]["adapter_version"] == "a3-defects4c-unified-diff-v1"
    assert value["prompt"]["max_input_tokens"] == 4096
    assert value["qualification"]["network"] == "unshared"
    assert value["qualification"]["cleanup_build_directory"] is True


def test_defects4c_prompt_adapter_requires_pure_diff() -> None:
    source = {"prompt": [
        {"role": "system", "content": "You are a C++ repair expert"},
        {"role": "user", "content": "buggy function and failing test\n\nPlease fix bugs in the function and tell me the complete fixed function."},
    ]}
    prompt = adapted_prompt(source, "lib/example.cpp")
    assert "--- a/lib/example.cpp" in prompt
    assert "+++ b/lib/example.cpp" in prompt
    assert prompt.endswith("Unified diff:\n")
    assert "complete fixed function" not in prompt


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("version",), "changed"),
        (("source", "plan_sha256"), "sha256:" + "0" * 64),
        (("source", "record_count"), 202),
        (("runtime", "rootfs_archive_sha256"), "sha256:" + "0" * 64),
        (("runtime", "bwrap_sha256"), "sha256:" + "0" * 64),
        (("prompt", "source_prompt_sha256"), "sha256:" + "0" * 64),
        (("prompt", "max_input_tokens"), 8192),
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
