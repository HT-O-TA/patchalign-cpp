from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.training.a5_dpo_common import dpo_rows, validate_config, variant


REPO = Path(__file__).resolve().parents[2]


def frozen_config() -> dict:
    return json.loads((REPO / "configs/training/a5_dpo_v1_1.json").read_text(encoding="utf-8"))


def test_frozen_a5_dpo_config_and_variants() -> None:
    config = frozen_config()
    validate_config(config)
    assert variant(config, "beta01") == {"name": "beta01", "role": "main", "beta": 0.1}
    assert variant(config, "beta03") == {"name": "beta03", "role": "control", "beta": 0.3}


def test_unknown_variant_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="unknown DPO variant"):
        variant(frozen_config(), "beta99")


def test_dpo_rows_strip_audit_metadata() -> None:
    pairs = [{
        "pair_id": "p1", "case_id": "c1", "prompt": "prompt",
        "chosen": {"response": "chosen", "terminal": "success"},
        "rejected": {"response": "rejected", "terminal": "apply_failed"},
    }]
    assert dpo_rows(pairs) == [{"prompt": "prompt", "chosen": "chosen", "rejected": "rejected"}]
