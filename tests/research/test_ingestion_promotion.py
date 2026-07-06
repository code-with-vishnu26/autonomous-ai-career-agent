"""Phase 26 / ADR-0052: exhaustive validation of the promotion boundary."""

from __future__ import annotations

from career_agent.domain.ingestion import ADD, TrustState
from research.ingestion_promotion import (
    all_decisions,
    exhaustive_invariant_search,
)


def test_decision_space_is_the_full_108_point_cross_product() -> None:
    decisions = all_decisions()
    assert len(decisions) == 3 * 3 * 2 * 2 * 3 == 108


def test_exhaustive_invariant_search_finds_no_violation() -> None:
    violations = exhaustive_invariant_search()
    assert violations == [], f"{len(violations)} promotion-invariant violation(s)"


def test_the_only_add_points_are_the_fully_admissible_ones() -> None:
    added = [c for c in all_decisions() if c.outcome == ADD]
    assert added, "expected at least one admissible ADD combination"
    for combo in added:
        assert combo.trust_state == TrustState.CONFIRMED
        assert combo.confirmation_kind == "binding"
        assert combo.evidence_valid is True
        assert combo.conflict is False
        assert combo.profile_state == "absent"
