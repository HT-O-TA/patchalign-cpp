import json
from pathlib import Path

import pytest

from scripts.baseline.run_a3_baseline import build_prompt, render_model_input
from scripts.baseline.score_a3_baseline import (
    A31_SCORING_PROTOCOL,
    STRICT_SCORING_PROTOCOL,
    load_scoring_protocol,
    normalized_command,
    prepare_patch_text,
    summarize,
)


ROOT = Path(__file__).resolve().parents[2]


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {
            "tokenize": False,
            "add_generation_prompt": True,
            "enable_thinking": False,
        }
        return "CHAT:" + messages[0]["content"]


def test_prompt_contains_only_public_evidence_and_buggy_code() -> None:
    prompt = build_prompt(
        {"task_level": "function"},
        "int main(){return 1;}\n",
        {"input": "public-input\n", "output": "public-output\n"},
        "main.cpp",
    )
    assert "public-input" in prompt
    assert "public-output" in prompt
    assert "int main(){return 1;}" in prompt
    assert "--- a/main.cpp" in prompt
    assert "fixed.cpp" not in prompt
    assert "hidden" not in prompt.lower()
    assert "gold patch" not in prompt.lower()


def test_model_input_modes_preserve_canonical_prompt() -> None:
    tokenizer = FakeTokenizer()
    assert render_model_input(tokenizer, "PROMPT", "raw_completion") == "PROMPT"
    assert (
        render_model_input(tokenizer, "PROMPT", "chat_non_thinking")
        == "CHAT:PROMPT"
    )


def test_normalized_command_uses_protocol_status_names() -> None:
    result = {
        "status": "pass",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
    }
    normalized = normalized_command(result)
    assert normalized["status"] == "passed"
    assert "stdout" not in normalized
    assert "stderr" not in normalized


def make_record(task_level: str, classification: str) -> dict[str, object]:
    success = classification == "success"
    stages = {
        name: {"status": "passed" if success else "not_run"}
        for name in ("parse", "policy", "apply", "build", "public", "hidden", "regression")
    }
    if classification == "parse_failed":
        stages["parse"] = {"status": "failed"}
    return {
        "task_level": task_level,
        "terminal_classification": classification,
        "success": success,
        "stages": stages,
    }


def test_summary_keeps_frozen_slice_denominators() -> None:
    records = [
        make_record("function", "success"),
        make_record("function", "parse_failed"),
        make_record("file_window", "success"),
    ]
    result = summarize(records)
    assert result["all"]["counts"]["total"] == 3
    assert result["function"]["counts"]["total"] == 2
    assert result["file_window"]["counts"]["total"] == 1
    assert result["function"]["counts"]["success"] == 1
    assert result["function"]["counts"]["format_violations"] == 1


def test_a31_scoring_protocol_is_frozen() -> None:
    config = load_scoring_protocol(
        ROOT / "configs" / "evaluation" / "a3_scoring_v2.json"
    )
    assert config["version"] == A31_SCORING_PROTOCOL
    assert config["transport_normalization"]["maximum_added_bytes"] == 1


def test_a31_scoring_protocol_rejects_semantic_drift(tmp_path: Path) -> None:
    source = ROOT / "configs" / "evaluation" / "a3_scoring_v2.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    config["forbidden_transforms"] = []
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen semantics"):
        load_scoring_protocol(changed)


def test_prepare_patch_text_preserves_v1_and_versions_v2() -> None:
    raw = "--- a/main.cpp\n+++ b/main.cpp\n@@ -1 +1 @@\n-old\n+new"
    assert prepare_patch_text(raw, STRICT_SCORING_PROTOCOL) == (raw, False)
    assert prepare_patch_text(raw, A31_SCORING_PROTOCOL) == (raw + "\n", True)


def test_a31_summary_records_transport_normalization() -> None:
    records = [
        make_record("function", "parse_failed"),
        make_record("file_window", "success"),
    ]
    for index, record in enumerate(records):
        record["scoring_protocol_version"] = A31_SCORING_PROTOCOL
        record["transport_normalization"] = {
            "rule": "append_one_lf_if_nonempty_and_missing",
            "terminal_lf_added": index == 0,
            "added_bytes": int(index == 0),
        }
    result = summarize(records)
    assert result["version"] == "a3-baseline-score-v2"
    assert result["scoring_protocol_version"] == A31_SCORING_PROTOCOL
    assert result["transport_normalization"]["terminal_lf_added"] == 1
    assert result["transport_normalization"]["raw_prediction_hash_preserved"] is True
