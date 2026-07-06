"""Phase 26 / ADR-0052: pure ingestion trust-model + promotion boundary."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.ingestion import (
    ADD,
    NO_OP,
    REJECT,
    REQUIRES_RESOLUTION,
    EvidenceSpan,
    FactProposal,
    PromotionConfirmation,
    TrustState,
    compute_binding_digest,
    confirmation_digest,
    detect_conflicts,
    evidence_digest,
    promote,
    span_text_digest,
    validate_span,
)


def _span(text: str, start: int, end: int) -> EvidenceSpan:
    return EvidenceSpan(
        document_digest="doc",
        source_type="text",
        start_offset=start,
        end_offset=end,
        text_digest=span_text_digest(text, start, end),
        extraction_method="test",
    )


def _proposal(
    *,
    value: str = "ada@example.com",
    field: str = "basics.email",
    trust: TrustState = TrustState.CONFIRMED,
    spans: list[EvidenceSpan] | None = None,
    conflicts: list[str] | None = None,
) -> FactProposal:
    spans = spans if spans is not None else [_span("x " + value, 2, 2 + len(value))]
    base = FactProposal(
        proposal_id="p1",
        field_path=field,
        proposed_value=value,
        evidence_spans=spans,
        extraction_method="test",
        trust_state=trust,
        conflict_ids=conflicts or [],
        source_document_digest="doc",
        binding_digest="",
    )
    return base.model_copy(update={"binding_digest": compute_binding_digest(base)})


def _binding_confirmation(proposal: FactProposal) -> PromotionConfirmation:
    return PromotionConfirmation(
        proposal_id=proposal.proposal_id,
        confirmation_digest=compute_binding_digest(proposal),
        confirmed_by="ada",
        confirmed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


# --------------------------------------------------------------------------
# Evidence span validation (Section 4): Unicode, CJK, emoji, CRLF, repeats,
# empty, invalid, drift.
# --------------------------------------------------------------------------


def test_valid_span_round_trips_across_unicode_cjk_emoji() -> None:
    for text in ("café résumé", "软件工程师 简历", "shipped 🚀 v2", "plain ascii"):
        span = _span(text, 0, len(text))
        assert validate_span(text, span) is True


def test_span_offsets_are_over_normalized_text_not_raw_crlf() -> None:
    # The parser normalizes CRLF->LF before offsets are taken; a span over
    # the normalized text validates.
    normalized = "line one\nline two"
    span = _span(normalized, 9, 17)
    assert normalized[9:17] == "line two"
    assert validate_span(normalized, span) is True


def test_repeated_text_keeps_distinct_offset_identity() -> None:
    text = "Python and Python and Python"
    first = _span(text, 0, 6)
    third = _span(text, 22, 28)
    # Location identity is offset-specific and distinct...
    assert (first.start_offset, first.end_offset) != (
        third.start_offset,
        third.end_offset,
    )
    assert validate_span(text, first) and validate_span(text, third)
    # ...and a span whose offsets point at genuinely different content (with
    # a stale digest) is invalid -- so a span can never silently rebind to
    # the wrong, differing text.
    other = "Rust here instead now here!!"
    assert validate_span(other, first) is False


def test_empty_and_out_of_range_and_reversed_spans_are_invalid_or_empty() -> None:
    text = "abc"
    empty = _span(text, 1, 1)  # empty but in range: valid, digests empty string
    assert validate_span(text, empty) is True
    out_of_range = empty.model_copy(update={"start_offset": 0, "end_offset": 99})
    assert validate_span(text, out_of_range) is False
    reversed_span = empty.model_copy(update={"start_offset": 2, "end_offset": 1})
    assert validate_span(text, reversed_span) is False


def test_source_drift_invalidates_a_previously_valid_span() -> None:
    original = "Reduced runtime by 40%"
    span = _span(original, 0, len(original))
    assert validate_span(original, span) is True
    drifted = "Reduced runtime by 90%"  # same offsets, changed bytes
    assert validate_span(drifted, span) is False


def test_evidence_digest_is_order_independent_and_dedup_stable() -> None:
    text = "a b c"
    s1, s2 = _span(text, 0, 1), _span(text, 2, 3)
    assert evidence_digest([s1, s2]) == evidence_digest([s2, s1])  # order
    assert evidence_digest([s1, s1, s2]) == evidence_digest([s1, s2])  # duplicates


# --------------------------------------------------------------------------
# Confirmation binding (Section 10 / I15-I17): replay, value, source drift.
# --------------------------------------------------------------------------


def test_confirmation_digest_is_proposal_value_and_source_specific() -> None:
    base = dict(
        proposal_id="p1",
        field_path="basics.email",
        proposed_value="a@x.com",
        source_document_digest="doc",
        evidence_spans=[],
    )
    d = confirmation_digest(**base)  # type: ignore[arg-type]
    assert confirmation_digest(**{**base, "proposal_id": "p2"}) != d  # type: ignore[arg-type]
    assert confirmation_digest(**{**base, "proposed_value": "b@x.com"}) != d  # type: ignore[arg-type]
    assert confirmation_digest(**{**base, "source_document_digest": "doc2"}) != d  # type: ignore[arg-type]


def test_confirmation_replayed_on_a_different_proposal_is_rejected() -> None:
    proposal_a = _proposal(value="a@x.com")
    proposal_b = _proposal(value="b@x.com")
    confirmation_for_a = _binding_confirmation(proposal_a)
    # Using A's confirmation to promote B fails: recomputed digest differs.
    decision = promote(proposal_b, confirmation_for_a, None, evidence_valid=True)
    assert decision.outcome == REJECT
    assert decision.reason == "CONFIRMATION_MISMATCH"


def test_value_drift_after_confirmation_is_rejected() -> None:
    proposal = _proposal(value="a@x.com")
    confirmation = _binding_confirmation(proposal)
    tampered = proposal.model_copy(update={"proposed_value": "evil@x.com"})
    decision = promote(tampered, confirmation, None, evidence_valid=True)
    assert decision.outcome == REJECT
    assert decision.reason == "CONFIRMATION_MISMATCH"


# --------------------------------------------------------------------------
# promote(): per-outcome + confidence-is-not-a-factor.
# --------------------------------------------------------------------------


def test_all_admissible_into_empty_field_adds() -> None:
    proposal = _proposal()
    decision = promote(
        proposal, _binding_confirmation(proposal), None, evidence_valid=True
    )
    assert decision.outcome == ADD


def test_same_existing_value_is_a_noop() -> None:
    proposal = _proposal(value="a@x.com")
    decision = promote(
        proposal, _binding_confirmation(proposal), "a@x.com", evidence_valid=True
    )
    assert decision.outcome == NO_OP


def test_different_existing_value_requires_resolution_never_overwrites() -> None:
    proposal = _proposal(value="new@x.com")
    decision = promote(
        proposal, _binding_confirmation(proposal), "old@x.com", evidence_valid=True
    )
    assert decision.outcome == REQUIRES_RESOLUTION
    assert decision.reason == "WOULD_OVERWRITE_DIFFERENT_VALUE"


def test_unverified_and_rejected_never_add() -> None:
    for trust in (TrustState.UNVERIFIED, TrustState.REJECTED):
        proposal = _proposal(trust=trust)
        decision = promote(
            proposal, _binding_confirmation(proposal), None, evidence_valid=True
        )
        assert decision.outcome != ADD


def test_conflict_blocks_promotion() -> None:
    proposal = _proposal(conflicts=["p2"])
    decision = promote(
        proposal, _binding_confirmation(proposal), None, evidence_valid=True
    )
    assert decision.outcome == REQUIRES_RESOLUTION
    assert decision.reason == "UNRESOLVED_CONFLICT"


def test_invalid_evidence_blocks_promotion() -> None:
    proposal = _proposal()
    decision = promote(
        proposal, _binding_confirmation(proposal), None, evidence_valid=False
    )
    assert decision.outcome == REJECT
    assert decision.reason == "INVALID_EVIDENCE"


def test_promote_has_no_confidence_parameter() -> None:
    """I10 / Family N: confidence cannot authorize promotion -- it is not an
    input to the boundary at all."""
    import inspect

    params = set(inspect.signature(promote).parameters)
    assert params == {"proposal", "confirmation", "current_value", "evidence_valid"}
    for forbidden in ("confidence", "score", "certainty"):
        assert forbidden not in params


# --------------------------------------------------------------------------
# Conflict detection (Section 7).
# --------------------------------------------------------------------------


def test_same_scalar_field_different_values_conflict() -> None:
    a = _proposal(value="hyderabad@x.com").model_copy(update={"proposal_id": "a"})
    b = _proposal(value="bengaluru@x.com").model_copy(update={"proposal_id": "b"})
    conflicts = detect_conflicts([a, b])
    assert conflicts == {"a": ["b"], "b": ["a"]}


def test_same_scalar_field_same_value_does_not_conflict() -> None:
    a = _proposal(value="same@x.com").model_copy(update={"proposal_id": "a"})
    b = _proposal(value="same@x.com").model_copy(update={"proposal_id": "b"})
    assert detect_conflicts([a, b]) == {}


def test_two_different_skills_never_conflict() -> None:
    a = _proposal(value="Python", field="skills").model_copy(
        update={"proposal_id": "a"}
    )
    b = _proposal(value="Rust", field="skills").model_copy(update={"proposal_id": "b"})
    assert detect_conflicts([a, b]) == {}
