from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.data.audit_data_v2_github_detail_early_stop import reconstruct


COMMON = {
    "version": "data-v2-github-detail-pilot-v1",
    "config_sha256": "sha256:" + "1" * 64,
    "script_sha256": "sha256:" + "2" * 64,
    "git_commit": "a" * 40,
    "selection_sha256": "sha256:" + "3" * 64,
}


def config() -> dict:
    return {
        "source_run": {
            "version": COMMON["version"],
            "git_commit": COMMON["git_commit"],
            "config": {"sha256": COMMON["config_sha256"]},
            "script": {"sha256": COMMON["script_sha256"]},
            "selected_candidates": {
                "count": 200,
                "sha256": COMMON["selection_sha256"],
            },
            "slurm_job_id": 7,
        },
        "outcome_gate": {
            "minimum_records": 50,
            "minimum_split_records": {"train": 40, "validation": 10},
            "minimum_split_repositories": {"train": 30, "validation": 8},
        },
    }


def selected() -> list[dict]:
    rows = []
    for index in range(200):
        split = "train" if index < 160 else "validation"
        candidate_id = "ghpr-" + hashlib.sha256(str(index).encode()).hexdigest()[:24]
        rows.append(
            {
                "candidate_id": candidate_id,
                "projected_split": split,
                "repository_split_group": f"github.com/{split}/repo-{index:03d}",
                "detail_pilot_order": index,
            }
        )
    return rows


def checkpoint(path: Path, *, accepted: bool, reason: str, projection: dict | None, **bindings: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        **COMMON,
        **bindings,
        "request_url": "https://api.github.com/example",
        "response": {"sha256": "sha256:" + "4" * 64, "http_status": 200},
        "accepted": accepted,
        "reason": reason,
        "projection": projection,
    }
    path.write_text(json.dumps(value), encoding="utf-8")


def make_prefix(root: Path, rows: list[dict]) -> None:
    first = rows[0]
    detail = {
        "repository_split_group": first["repository_split_group"],
        "merge_commit_sha": "b" * 40,
    }
    checkpoint(
        root / "pull" / f'{first["candidate_id"]}.json',
        accepted=True,
        reason="selected",
        projection=detail,
        candidate_id=first["candidate_id"],
        stage="pull",
    )
    checkpoint(
        root / "issue" / f'{first["candidate_id"]}.json',
        accepted=True,
        reason="selected",
        projection={"number": 1, "state": "closed", "bug_label_matched": True},
        candidate_id=first["candidate_id"],
        stage="issue",
    )
    repo_id = hashlib.sha256(first["repository_split_group"].encode()).hexdigest()[:24]
    checkpoint(
        root / "license" / f"ghrepo-{repo_id}.json",
        accepted=True,
        reason="selected",
        projection={"spdx_id": "MIT"},
        repository_split_group=first["repository_split_group"],
        stage="license",
    )
    second = rows[1]
    checkpoint(
        root / "pull" / f'{second["candidate_id"]}.json',
        accepted=False,
        reason="changed_lines_out_of_range",
        projection=None,
        candidate_id=second["candidate_id"],
        stage="pull",
    )


def test_reconstructs_prefix_and_proves_train_gate_unreachable(tmp_path: Path) -> None:
    rows = selected()
    make_prefix(tmp_path, rows)
    decisions, qualified, summary = reconstruct(config(), rows, tmp_path)
    assert len(qualified) == 1
    assert summary["completed_prefix"] == 2
    assert summary["candidate_states"] == {
        "qualified": 1,
        "rejected": 1,
        "unstarted": 198,
    }
    assert summary["optimistic_upper_bound_split_records"] == {
        "train": 159,
        "validation": 40,
    }
    assert summary["outcome_gate_irrecoverable"] is False
    assert decisions[0]["state"] == "qualified"


def test_realistic_completed_prefix_makes_train_gate_irrecoverable(tmp_path: Path) -> None:
    rows = selected()
    make_prefix(tmp_path, rows)
    for row in rows[2:145]:
        checkpoint(
            tmp_path / "pull" / f'{row["candidate_id"]}.json',
            accepted=False,
            reason="rejected",
            projection=None,
            candidate_id=row["candidate_id"],
            stage="pull",
        )
    _decisions, _qualified, summary = reconstruct(config(), rows, tmp_path)
    assert summary["completed_prefix"] == 145
    assert summary["optimistic_upper_bound_split_records"]["train"] == 16
    assert summary["outcome_gate_reachability"]["train_minimum_records"] is False
    assert summary["outcome_gate_irrecoverable"] is True


def test_rejects_checkpoint_binding_drift(tmp_path: Path) -> None:
    rows = selected()
    make_prefix(tmp_path, rows)
    path = tmp_path / "pull" / f'{rows[0]["candidate_id"]}.json'
    value = json.loads(path.read_text())
    value["git_commit"] = "f" * 40
    path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="binding changed"):
        reconstruct(config(), rows, tmp_path)
