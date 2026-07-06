"""Phase 26 (ADR-0052): exhaustive verification of the promotion boundary.

Mirrors ``research/execution_safety.py``: a top-level, offline module (not
in the shipped package) importing the production promotion boundary
unmodified and enumerating its entire finite decision space. An empty
counterexample list is a proof over that space, not evidence from
examples. Nothing here makes a network/LLM call or costs money.

Decision-space dimensions (fully enumerated):

    trust_state (3) x confirmation kind (3: none / binding / non-binding)
        x evidence_valid (2) x conflict (2) x profile_state (3)
    = 3 * 3 * 2 * 2 * 3 = 108 combinations.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from career_agent.domain.ingestion import (
    ADD,
    EvidenceSpan,
    FactProposal,
    PromotionConfirmation,
    TrustState,
    compute_binding_digest,
    promote,
)

_TRUST_STATES = tuple(TrustState)
_CONFIRMATION_KINDS = ("none", "binding", "non_binding")
_EVIDENCE = (True, False)
_CONFLICT = (True, False)
_PROFILE_STATES = ("absent", "same", "different")

_PROPOSED_VALUE = "the-proposed-value"


def _proposal(trust_state: TrustState, conflict: bool) -> FactProposal:
    span = EvidenceSpan(
        document_digest="docsha",
        source_type="text",
        start_offset=0,
        end_offset=5,
        text_digest="td",
        extraction_method="test",
    )
    base = FactProposal(
        proposal_id="p1",
        field_path="basics.email",
        proposed_value=_PROPOSED_VALUE,
        evidence_spans=[span],
        extraction_method="test",
        trust_state=trust_state,
        conflict_ids=["p2"] if conflict else [],
        source_document_digest="docsha",
        binding_digest="",
    )
    return base.model_copy(update={"binding_digest": compute_binding_digest(base)})


def _confirmation(
    kind: str, proposal: FactProposal
) -> PromotionConfirmation | None:
    if kind == "none":
        return None
    digest = (
        compute_binding_digest(proposal) if kind == "binding" else "wrong-digest"
    )
    from datetime import UTC, datetime

    return PromotionConfirmation(
        proposal_id="p1",
        confirmation_digest=digest,
        confirmed_by="test",
        confirmed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _current_value(profile_state: str) -> str | None:
    return {
        "absent": None,
        "same": _PROPOSED_VALUE,
        "different": "a-different-trusted-value",
    }[profile_state]


@dataclass(frozen=True)
class Combination:
    """One enumerated input point and the decision ``promote`` returned for it."""

    trust_state: TrustState
    confirmation_kind: str
    evidence_valid: bool
    conflict: bool
    profile_state: str
    outcome: str
    reason: str


def all_decisions() -> list[Combination]:
    """Evaluate ``promote`` at every one of the 108 points in its space."""
    rows: list[Combination] = []
    for trust, conf_kind, evidence, conflict, profile in itertools.product(
        _TRUST_STATES, _CONFIRMATION_KINDS, _EVIDENCE, _CONFLICT, _PROFILE_STATES
    ):
        proposal = _proposal(trust, conflict)
        decision = promote(
            proposal,
            _confirmation(conf_kind, proposal),
            _current_value(profile),
            evidence_valid=evidence,
        )
        rows.append(
            Combination(
                trust, conf_kind, evidence, conflict, profile,
                decision.outcome, decision.reason,
            )
        )
    return rows


@dataclass(frozen=True)
class InvariantViolation:
    """A combination that violated a named safety invariant. Never expected."""

    invariant: str
    combination: Combination


def exhaustive_invariant_search() -> list[InvariantViolation]:
    """Check every combination against the promotion safety invariants."""
    violations: list[InvariantViolation] = []
    for combo in all_decisions():
        added = combo.outcome == ADD
        # The complete positive characterization: ADD iff all admissible.
        admissible = (
            combo.trust_state == TrustState.CONFIRMED
            and combo.confirmation_kind == "binding"
            and combo.evidence_valid
            and not combo.conflict
            and combo.profile_state == "absent"
        )
        confirmed = combo.trust_state == TrustState.CONFIRMED
        rejected = combo.trust_state == TrustState.REJECTED
        checks: list[tuple[str, bool]] = [
            ("I1_unconfirmed_never_added", added and not confirmed),
            ("I2_rejected_never_added", added and rejected),
            ("I3_conflict_never_added", added and combo.conflict),
            ("I4_invalid_evidence_never_added", added and not combo.evidence_valid),
            (
                "I5_nonbinding_confirmation_never_added",
                added and combo.confirmation_kind != "binding",
            ),
            (
                "I9_different_value_never_overwritten",
                added and combo.profile_state == "different",
            ),
            ("positive_characterization", added != admissible),
        ]
        for name, violated in checks:
            if violated:
                violations.append(InvariantViolation(name, combo))
    return violations
