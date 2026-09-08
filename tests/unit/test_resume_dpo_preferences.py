from __future__ import annotations

import pytest

from scripts.preference.audit_resume_dpo_preferences import pair_decision


def test_timeout_only_pair_is_excluded() -> None:
    assert pair_decision({"reason": "timeout_tiebreak"}) == (False, "timeout_tiebreak_excluded")


def test_terminal_stage_pair_requires_strict_rank() -> None:
    assert pair_decision({"reason": "terminal_stage", "chosen_rank": [9, 1], "rejected_rank": [5, 1]}) == (
        True,
        "terminal_stage_strictly_better",
    )
    with pytest.raises(RuntimeError, match="not strictly ranked"):
        pair_decision({"reason": "terminal_stage", "chosen_rank": [5, 1], "rejected_rank": [5, 1]})
