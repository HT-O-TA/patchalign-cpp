from __future__ import annotations

import json
from pathlib import Path

import pytest

from patchalign import cli
from patchalign.inference import build_prompt


REQUEST = {
    "task_level": "function",
    "allowed_path": "main.cpp",
    "buggy_code": "int main() { return 1; }\n",
    "public_test": {"input": "\n", "output": "0\n"},
}


def write_request(path: Path, value: object = REQUEST) -> None:
    path.write_text(json.dumps(value), encoding="utf-8", newline="\n")


def test_prompt_command_renders_frozen_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    request = tmp_path / "request.json"
    write_request(request)
    monkeypatch.setattr("sys.argv", ["patchalign-cpp", "prompt", "--request", str(request)])

    cli.main()

    captured = capsys.readouterr()
    assert captured.out == build_prompt(REQUEST)
    assert captured.err == ""


def test_infer_command_writes_patch_and_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = tmp_path / "request.json"
    patch_path = tmp_path / "candidate.patch"
    metadata_path = tmp_path / "metadata.json"
    write_request(request)
    observed: dict[str, object] = {}

    def fake_generate(request_value: dict, model_path: Path, adapter_path: Path, **kwargs: object) -> dict:
        observed.update(request=request_value, model_path=model_path, adapter_path=adapter_path, kwargs=kwargs)
        return {
            "patch": "--- a/main.cpp\n+++ b/main.cpp\n@@ -1 +1 @@\n-old\n+new\n",
            "patch_sha256": "sha256:test",
            "input_tokens": 10,
        }

    monkeypatch.setattr(cli, "generate_patch", fake_generate)
    monkeypatch.setattr(
        "sys.argv",
        [
            "patchalign-cpp",
            "infer",
            "--request",
            str(request),
            "--model-path",
            "/models/base",
            "--adapter-path",
            "/models/adapter",
            "--output",
            str(patch_path),
            "--metadata",
            str(metadata_path),
        ],
    )

    cli.main()

    assert observed["request"] == REQUEST
    assert observed["model_path"] == Path("/models/base")
    assert observed["adapter_path"] == Path("/models/adapter")
    assert observed["kwargs"] == {
        "seed": 20260830,
        "max_input_tokens": 4096,
        "max_new_tokens": 512,
        "local_files_only": True,
    }
    assert patch_path.read_text(encoding="utf-8").endswith("+new\n")
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {
        "input_tokens": 10,
        "patch_sha256": "sha256:test",
    }


def test_prompt_command_reports_invalid_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    request = tmp_path / "request.json"
    write_request(request, {"task_level": "function"})
    monkeypatch.setattr("sys.argv", ["patchalign-cpp", "prompt", "--request", str(request)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "request fields must be exactly" in capsys.readouterr().err
