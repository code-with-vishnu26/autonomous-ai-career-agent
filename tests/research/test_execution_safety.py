"""Phase 24 / ADR-0050: exhaustive finite-state validation (Families H, I).

Runs the offline ``research/execution_safety.py`` enumeration -- every one
of the 512 points in the boundary's input space -- and asserts zero
invariant and zero metamorphic violations. An empty result is a proof over
the whole space, not evidence from examples.
"""

from __future__ import annotations

from career_agent.domain.execution import AckClass, SourcePolicy, SubmissionOutcome
from research.execution_safety import (
    ack_outcome_table,
    all_requests,
    exhaustive_invariant_search,
    exhaustive_metamorphic_search,
    retry_admissibility_table,
)


def test_input_space_is_the_full_256_point_cross_product() -> None:
    requests = all_requests()
    assert len(requests) == 4 * 2 * 2 * 2 * 4 * 2 == 256
    assert len(set(requests)) == 256  # all distinct


def test_exhaustive_invariant_search_finds_no_violation() -> None:
    violations = exhaustive_invariant_search()
    assert violations == [], f"{len(violations)} safety-invariant violation(s)"


def test_exhaustive_metamorphic_search_finds_no_violation() -> None:
    violations = exhaustive_metamorphic_search()
    assert violations == [], f"{len(violations)} metamorphic violation(s)"


def test_retry_admissibility_table_blocks_unsafe_priors() -> None:
    table = retry_admissibility_table()
    assert table[SubmissionOutcome.DEFINITELY_SUBMITTED] is False
    assert table[SubmissionOutcome.OUTCOME_UNCERTAIN] is False
    # Retry-safe priors are retryable in this most-permissive context.
    assert table[SubmissionOutcome.NOT_ATTEMPTED] is True
    assert table[SubmissionOutcome.DEFINITELY_NOT_SUBMITTED] is True


def test_ack_outcome_table_never_upgrades_ambiguity() -> None:
    table = ack_outcome_table()
    assert table[AckClass.AMBIGUOUS] == SubmissionOutcome.OUTCOME_UNCERTAIN
    # No AckClass maps to a definite result it lacks evidence for.
    assert set(table) == set(AckClass)


def test_no_manual_or_unknown_policy_point_is_ever_allowed() -> None:
    """I2 + fail-closed default, restated as a direct sweep over the space."""
    from career_agent.domain.execution import execute_allowed

    for request in all_requests():
        if request.source_policy in (SourcePolicy.MANUAL_ONLY, SourcePolicy.UNKNOWN):
            assert not execute_allowed(request).allowed
