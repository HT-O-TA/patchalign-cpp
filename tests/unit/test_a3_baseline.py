from scripts.baseline.run_a3_baseline import build_prompt, render_model_input
from scripts.baseline.score_a3_baseline import normalized_command, summarize


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
