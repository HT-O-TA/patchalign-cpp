from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.training.train_a3_sft_pilot import (
    build_training_prompt,
    encode_example,
    normalized_target,
    training_order,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]


class FakeTokenizer:
    eos_token_id = 99

    def __call__(self, text: str, *, add_special_tokens: bool) -> dict[str, list[int]]:
        prefix = [1] if add_special_tokens else []
        return {"input_ids": prefix + [2] * len(text)}


@pytest.fixture
def config() -> dict:
    return json.loads(
        (ROOT / "configs/training/a3_sft_pilot_v1.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def sample() -> dict:
    return json.loads(
        (
            ROOT
            / "tests/fixtures/a0/sample-v0.2.function-multi-line.valid.json"
        ).read_text(encoding="utf-8")
    )


def test_frozen_pilot_config_is_accepted(config: dict) -> None:
    validate_config(config)


def test_changed_training_setting_is_rejected(config: dict) -> None:
    changed = copy.deepcopy(config)
    changed["training"]["epochs"] = 2
    with pytest.raises(RuntimeError, match="epochs"):
        validate_config(changed)


def test_training_prompt_has_no_gold_patch(sample: dict) -> None:
    prompt = build_training_prompt(sample)
    assert prompt.endswith("Unified diff:\n")
    assert sample["allowed_paths"][0] in prompt
    assert sample["context"]["buggy_code"].rstrip("\n") in prompt
    assert sample["gold_patch"] not in prompt


def test_target_gets_at_most_one_terminal_lf(sample: dict) -> None:
    target = normalized_target(sample)
    assert target.endswith("\n")
    sample["gold_patch"] = target.rstrip("\n")
    assert normalized_target(sample) == target


def test_prompt_tokens_are_masked_and_target_is_supervised(sample: dict) -> None:
    encoded = encode_example(FakeTokenizer(), sample, 10000)
    assert encoded["labels"][: encoded["prompt_tokens"]] == [-100] * encoded["prompt_tokens"]
    assert all(value != -100 for value in encoded["labels"][encoded["prompt_tokens"] :])
    assert encoded["input_ids"][-1] == FakeTokenizer.eos_token_id
    assert encoded["labels"][-1] == FakeTokenizer.eos_token_id


def test_encoding_fails_closed_instead_of_truncating(sample: dict) -> None:
    with pytest.raises(RuntimeError, match="exceeds"):
        encode_example(FakeTokenizer(), sample, 10)


def test_training_order_is_deterministic_and_epoch_complete() -> None:
    first = training_order(12, 2, 20260830)
    second = training_order(12, 2, 20260830)
    assert first == second
    assert first[0] != first[1]
    assert all(sorted(epoch) == list(range(12)) for epoch in first)
