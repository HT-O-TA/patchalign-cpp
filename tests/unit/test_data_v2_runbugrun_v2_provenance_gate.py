from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.check_data_v2_runbugrun_v2_provenance_gate import validate


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_runbugrun_v2_provenance_gate_v1.json").read_text(encoding="utf-8"))


def test_gate_allows_metadata_but_no_content_training_or_redistribution() -> None:
    config = load_config()
    validate(config)
    decision = config["decision"]
    assert decision["metadata_and_schema_research_authorized"] is True
    assert decision["full_release_download_authorized"] is False
    assert decision["program_or_test_content_acquisition_authorized"] is False
    assert decision["data_v2_training_admission_authorized"] is False
    assert decision["sft_authorized"] is False
    assert decision["dpo_authorized"] is False


@pytest.mark.parametrize(
    "key",
    [
        "full_release_download_authorized",
        "program_or_test_content_acquisition_authorized",
        "data_v2_training_admission_authorized",
        "sft_authorized",
        "dpo_authorized",
        "redistribution_authorized",
    ],
)
def test_gate_rejects_silent_authorization(key: str) -> None:
    config = copy.deepcopy(load_config())
    config["decision"][key] = True
    with pytest.raises(RuntimeError, match="fail-closed boundary weakened"):
        validate(config)


def test_gate_rejects_source_identity_drift() -> None:
    config = copy.deepcopy(load_config())
    config["source"]["revision"] = "0" * 40
    with pytest.raises(RuntimeError, match="source revision changed"):
        validate(config)

