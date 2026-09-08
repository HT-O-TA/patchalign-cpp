from __future__ import annotations

from scripts.evaluation.a5_dpo_dev_common import select_variant


def metric(*, passed: int, hidden: int, public: int, build: int, apply: int, timeouts: int = 0, regressions: int = 0) -> dict[str, int]:
    return {
        "pass_count": passed,
        "hidden_test_success": hidden,
        "public_test_success": public,
        "compile_success": build,
        "apply_success": apply,
        "timeouts": timeouts,
        "regression_failures": regressions,
    }


def test_positive_eligible_variant_wins_by_frozen_funnel() -> None:
    result = select_variant({
        "baseline": metric(passed=1, hidden=2, public=4, build=8, apply=10),
        "beta01": metric(passed=2, hidden=2, public=4, build=8, apply=10),
        "beta03": metric(passed=1, hidden=3, public=5, build=9, apply=11),
    })
    assert result["selected"] == "beta01"
    assert result["selected_is_promotable"] is True


def test_non_degradation_constraints_block_positive_variant() -> None:
    result = select_variant({
        "baseline": metric(passed=1, hidden=2, public=4, build=8, apply=10),
        "beta01": metric(passed=3, hidden=3, public=5, build=9, apply=11, timeouts=1),
        "beta03": metric(passed=2, hidden=2, public=4, build=8, apply=10),
    })
    assert result["eligible"]["beta01"] is False
    assert result["selected"] == "beta03"


def test_no_positive_signal_uses_lower_risk() -> None:
    result = select_variant({
        "baseline": metric(passed=2, hidden=3, public=5, build=8, apply=10, timeouts=2, regressions=1),
        "beta01": metric(passed=1, hidden=3, public=5, build=8, apply=10, timeouts=0, regressions=1),
        "beta03": metric(passed=1, hidden=2, public=5, build=8, apply=10, timeouts=2, regressions=0),
    })
    assert result["selected"] == "beta03"
    assert result["reason"] == "lower_risk_negative_or_no_improvement"


def test_exact_tie_prefers_beta03() -> None:
    tied = metric(passed=1, hidden=2, public=4, build=8, apply=10)
    result = select_variant({"baseline": tied, "beta01": tied, "beta03": tied})
    assert result["selected"] == "beta03"
