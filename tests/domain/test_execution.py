"""Phase 24 / ADR-0050: execution-safety boundary unit tests.

Families A-D from the brief's test strategy, at the pure-domain level;
the full exhaustive finite-state validation (Family H) and metamorphic
properties (Family I) live in ``tests/research/test_execution_safety.py``.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from career_agent.domain.execution import (
    AckClass,
    ExecutionRequest,
    SourcePolicy,
    SubmissionOutcome,
    confirmed_artifact_digest,
    execute_allowed,
    outcome_from_ack,
    resolve_source_policy,
    retry_allowed,
)


def _all_good(**overrides: object) -> ExecutionRequest:
    """The one fully-permissive request, with targeted adverse overrides."""
    base = {
        "source_policy": SourcePolicy.AUTOMATED,
        "executor_available": True,
        "confirmation_present": True,
        "artifact_matches": True,
        "prior_outcome": SubmissionOutcome.NOT_ATTEMPTED,
        "journal_has_unresolved_intent": False,
    }
    base.update(overrides)
    return ExecutionRequest(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Family A: acknowledgement -> outcome mapping (the "ambiguous stays
# ambiguous" law)
# --------------------------------------------------------------------------


def test_ack_mapping_is_total_and_ambiguous_stays_uncertain() -> None:
    assert outcome_from_ack(AckClass.DEFINITE_SUCCESS) == (
        SubmissionOutcome.DEFINITELY_SUBMITTED
    )
    assert outcome_from_ack(AckClass.DEFINITE_FAILURE) == (
        SubmissionOutcome.DEFINITELY_NOT_SUBMITTED
    )
    # The load-bearing row: no fabricated certainty from ambiguous evidence.
    assert outcome_from_ack(AckClass.AMBIGUOUS) == SubmissionOutcome.OUTCOME_UNCERTAIN


def test_no_ack_class_maps_to_a_definite_result_from_ambiguity() -> None:
    """Every AckClass is handled -- the mapping is total, no KeyError."""
    for ack in AckClass:
        assert outcome_from_ack(ack) in SubmissionOutcome


# --------------------------------------------------------------------------
# Family B: retry admissibility
# --------------------------------------------------------------------------


def test_uncertain_and_submitted_are_never_retryable_even_at_best_context() -> None:
    """I3/I4: the mandatory safety property, under the friendliest inputs."""
    for outcome in (
        SubmissionOutcome.DEFINITELY_SUBMITTED,
        SubmissionOutcome.OUTCOME_UNCERTAIN,
    ):
        assert (
            retry_allowed(
                outcome,
                unresolved_intent=False,
                source_policy=SourcePolicy.AUTOMATED,
            )
            is False
        )


def test_pre_effect_failure_and_never_attempted_are_retryable_under_policy() -> None:
    """I7: a definite pre-effect failure may retry -- but only per policy."""
    for outcome in (
        SubmissionOutcome.NOT_ATTEMPTED,
        SubmissionOutcome.DEFINITELY_NOT_SUBMITTED,
    ):
        assert retry_allowed(
            outcome, unresolved_intent=False, source_policy=SourcePolicy.ASSISTED
        )
        # ...but not under a non-automatable policy.
        assert not retry_allowed(
            outcome, unresolved_intent=False, source_policy=SourcePolicy.MANUAL_ONLY
        )
        # ...and not with a dangling execution intent.
        assert not retry_allowed(
            outcome, unresolved_intent=True, source_policy=SourcePolicy.ASSISTED
        )


# --------------------------------------------------------------------------
# Family C: artifact integrity digest
# --------------------------------------------------------------------------


def test_artifact_digest_is_answer_order_invariant() -> None:
    a = confirmed_artifact_digest(
        opportunity_id="opp-1",
        rendered_content="resume",
        target="https://x/apply",
        tier="browser",
        normalized_answers={"q1": "yes", "q2": "no"},
    )
    b = confirmed_artifact_digest(
        opportunity_id="opp-1",
        rendered_content="resume",
        target="https://x/apply",
        tier="browser",
        normalized_answers={"q2": "no", "q1": "yes"},  # different insertion order
    )
    assert a == b


def test_artifact_digest_changes_when_any_submission_relevant_field_changes() -> None:
    base: dict[str, str] = dict(
        opportunity_id="opp-1",
        rendered_content="resume",
        target="https://x/apply",
        tier="browser",
    )
    original = confirmed_artifact_digest(**base)  # type: ignore[arg-type]
    for field, value in [
        ("rendered_content", "DIFFERENT"),
        ("opportunity_id", "opp-2"),
        ("target", "https://y/apply"),
        ("tier", "email"),
    ]:
        mutated = confirmed_artifact_digest(**{**base, field: value})  # type: ignore[arg-type]
        assert mutated != original, f"changing {field} must change the digest"


def test_artifact_digest_field_boundaries_do_not_collide() -> None:
    """A separator prevents ('ab','c') from colliding with ('a','bc')."""
    first = confirmed_artifact_digest(
        opportunity_id="ab", rendered_content="c", target="t", tier="browser"
    )
    second = confirmed_artifact_digest(
        opportunity_id="a", rendered_content="bc", target="t", tier="browser"
    )
    assert first != second


# --------------------------------------------------------------------------
# Family D: provider/source policy resolution (fail closed)
# --------------------------------------------------------------------------


def test_known_ats_kinds_resolve_to_assisted_never_automated() -> None:
    for ats_kind in ("greenhouse", "lever", "ashby"):
        assert resolve_source_policy("ats_api", ats_kind) == SourcePolicy.ASSISTED


def test_manual_only_sources_resolve_to_manual_only() -> None:
    for source in ("web_search", "career_page", "hn", "yc"):
        assert resolve_source_policy(source, None) == SourcePolicy.MANUAL_ONLY


def test_structured_source_without_automatable_target_fails_closed_to_manual() -> None:
    assert resolve_source_policy("ats_api", None) == SourcePolicy.MANUAL_ONLY
    assert resolve_source_policy("job_board", None) == SourcePolicy.MANUAL_ONLY


def test_unrecognized_source_is_unknown_and_fails_closed() -> None:
    decision = execute_allowed(
        _all_good(source_policy=resolve_source_policy("some_new_source", None))
    )
    assert not decision.allowed


def test_no_source_ever_resolves_to_automated() -> None:
    """ADR-0027 recorded every fully-automated direct-API path dead."""
    sources = ("ats_api", "yc", "hn", "career_page", "web_search", "job_board", "x")
    ats_kinds = (None, "greenhouse", "lever", "ashby", "unknown_ats")
    for source in sources:
        for ats_kind in ats_kinds:
            assert resolve_source_policy(source, ats_kind) != SourcePolicy.AUTOMATED


# --------------------------------------------------------------------------
# execute_allowed: each refusal reason + the single ALLOWED case
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"executor_available": False}, "REFUSED_NO_EXECUTOR"),
        ({"source_policy": SourcePolicy.UNKNOWN}, "REFUSED_UNKNOWN_SOURCE_POLICY"),
        ({"source_policy": SourcePolicy.MANUAL_ONLY}, "REFUSED_MANUAL_ONLY_SOURCE"),
        ({"confirmation_present": False}, "REFUSED_NO_CONFIRMATION"),
        ({"artifact_matches": False}, "REFUSED_ARTIFACT_MISMATCH"),
        (
            {"prior_outcome": SubmissionOutcome.DEFINITELY_SUBMITTED},
            "REFUSED_PRIOR_SUBMITTED",
        ),
        (
            {"prior_outcome": SubmissionOutcome.OUTCOME_UNCERTAIN},
            "REFUSED_PRIOR_UNCERTAIN",
        ),
        ({"journal_has_unresolved_intent": True}, "REFUSED_UNRESOLVED_INTENT"),
    ],
)
def test_each_adverse_condition_refuses_with_its_reason(
    override: dict, expected_reason: str
) -> None:
    decision = execute_allowed(_all_good(**override))
    assert decision.allowed is False
    assert decision.reason == expected_reason


def test_all_positive_conditions_yield_allowed() -> None:
    decision = execute_allowed(_all_good())
    assert decision.allowed is True
    assert decision.reason == "ALLOWED"


# --------------------------------------------------------------------------
# I16-I19 (structural): ranking/pareto/ATS/truthfulness are not even inputs
# to the permission decision, so none of them can authorize submission.
# --------------------------------------------------------------------------


def test_permission_inputs_exclude_quality_signals() -> None:
    field_names = {f.name for f in fields(ExecutionRequest)}
    for forbidden in (
        "ats_score",
        "ats_total",
        "ranking",
        "rank",
        "score",
        "pareto",
        "truthfulness",
        "confidence",
    ):
        assert forbidden not in field_names
    # It considers exactly these six safety factors, and nothing else.
    assert field_names == {
        "source_policy",
        "executor_available",
        "confirmation_present",
        "artifact_matches",
        "prior_outcome",
        "journal_has_unresolved_intent",
    }
