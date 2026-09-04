from pathlib import Path

import pytest

from scripts.external.finalize_pre_a4_readiness import load_bound


def test_readiness_binding_rejects_wrong_path() -> None:
    with pytest.raises(RuntimeError, match="readiness path changed"):
        load_bound(
            {"path": "/tmp/wrong.json", "sha256": "sha256:" + "0" * 64},
            "/tmp/expected.json",
        )


def test_readiness_binding_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    with pytest.raises(RuntimeError, match="readiness input missing"):
        load_bound(
            {"path": str(path), "sha256": "sha256:" + "0" * 64},
            str(path),
        )
