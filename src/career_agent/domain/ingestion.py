"""Evidence-grounded CV ingestion: the trust model and promotion boundary.

Phase 26 / ADR-0052. Pure domain layer: stdlib + pydantic only, no I/O, no
network, no LLM (domain-purity import-linter contract). Document parsing
and deterministic extraction live one layer out, in
``storage/cv_ingest.py``; this module defines *what an imported fact is*
and *the exact conditions under which one may become a trusted profile
fact*.

The load-bearing rule (ADR-0006 + ADR-0044): a ``MasterProfile`` field is
trusted evidence the truthfulness gate consumes. Nothing extracted from a
CV -- parser output, a regex match, an inferred value -- is trusted. It is
a :class:`FactProposal` in ``UNVERIFIED`` trust state, and it can only
become a profile fact through :func:`promote`, which fails closed: it
requires an explicit, content-bound confirmation, valid source-bound
evidence, no unresolved conflict, and no silent overwrite of a different
already-trusted value. Confidence is deliberately **not** modeled --
confidence is not truth, not confirmation, and not promotion permission,
so there is no scalar here that could be mistaken for any of those.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TrustState(StrEnum):
    """A proposal's trust state. There is deliberately no ``VERIFIED`` state.

    A promoted fact leaves the proposal layer entirely and becomes a
    ``MasterProfile`` field -- the profile *is* the verified store
    (ADR-0006), so "verified" is not a state a proposal sits in. ``conflict``
    is not a state either: it is a derived property (``conflict_ids``
    non-empty), kept separate so a system-detected conflict is never
    confused with a user action (confirm/reject).
    """

    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EvidenceSpan(BaseModel):
    """A source-bound pointer into one exact ingested document.

    Offsets index the *normalized* document text (CRLF/CR collapsed to LF
    once at parse time -- the one documented normalization rule; no Unicode
    re-composition, so the digest is over the exact post-normalization
    substring). ``text_digest`` is the SHA-256 of that substring, so a span
    can be re-validated against the document later and drift detected.
    """

    document_digest: str
    source_type: str
    start_offset: int
    end_offset: int
    text_digest: str
    extraction_method: str
    page_number: int | None = None
    paragraph_index: int | None = None


def span_text_digest(document_text: str, start: int, end: int) -> str:
    """The digest recorded for the substring ``document_text[start:end]``."""
    return _sha256(document_text[start:end])


def validate_span(document_text: str, span: EvidenceSpan) -> bool:
    """Does ``span`` cite real, unchanged text within this document?

    Enforces ``0 <= start <= end <= len`` and that the substring at those
    offsets still digests to the recorded ``text_digest``. A changed
    document (source drift) or an out-of-range offset both make this
    ``False`` -- and an invalid span can never authorize promotion (I4).
    """
    if not (0 <= span.start_offset <= span.end_offset <= len(document_text)):
        return False
    return span_text_digest(document_text, span.start_offset, span.end_offset) == (
        span.text_digest
    )


def evidence_digest(spans: list[EvidenceSpan]) -> str:
    """A stable digest over a proposal's evidence set.

    Order-independent (spans are sorted by their offsets/digest first), so
    two proposals citing the same spans in a different order bind
    identically, and duplicate spans do not multiply anything (I12).
    """
    keys = sorted(
        {
            f"{s.document_digest}:{s.start_offset}:{s.end_offset}:{s.text_digest}"
            for s in spans
        }
    )
    return _sha256("\x1f".join(keys))


class FactProposal(BaseModel):
    """One candidate fact extracted from a CV -- untrusted until promoted.

    ``binding_digest`` is computed once, at import, over the proposal's
    identity + value + source + evidence (see :func:`confirmation_digest`).
    It is what a later confirmation binds to: if the value, the source
    document, or the cited evidence changes afterward, the recomputed digest
    no longer matches and promotion fails closed (value/source/replay drift).
    """

    proposal_id: str
    field_path: str
    proposed_value: str
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    extraction_method: str
    trust_state: TrustState = TrustState.UNVERIFIED
    conflict_ids: list[str] = Field(default_factory=list)
    source_document_digest: str
    binding_digest: str


def confirmation_digest(
    *,
    proposal_id: str,
    field_path: str,
    proposed_value: str,
    source_document_digest: str,
    evidence_spans: list[EvidenceSpan],
) -> str:
    """Bind a confirmation to exact content -- proposal, value, source, evidence.

    This is an *integrity* digest for equality comparison, not a claim of
    human identity or cryptographic authenticity. Changing any bound field
    changes the digest, which is exactly what makes confirmation
    proposal-specific (I15), value-specific (I16), and source-specific
    (I17), and makes a confirmation for one proposal unusable on another
    (replay rejection).
    """
    return _sha256(
        "\x1f".join(
            [
                proposal_id,
                field_path,
                proposed_value,
                source_document_digest,
                evidence_digest(evidence_spans),
            ]
        )
    )


def compute_binding_digest(proposal: FactProposal) -> str:
    """Recompute a proposal's binding digest from its *current* content."""
    return confirmation_digest(
        proposal_id=proposal.proposal_id,
        field_path=proposal.field_path,
        proposed_value=proposal.proposed_value,
        source_document_digest=proposal.source_document_digest,
        evidence_spans=proposal.evidence_spans,
    )


@dataclass(frozen=True)
class PromotionConfirmation:
    """An explicit authorization to promote one exact proposal's content.

    Mirrors :class:`~career_agent.domain.models.HumanConfirmation`'s
    token-binding discipline: ``confirmation_digest`` names the exact
    content authorized, not "this proposal" in the abstract.
    """

    proposal_id: str
    confirmation_digest: str
    confirmed_by: str
    confirmed_at: datetime


# Merge/promotion outcomes (closed vocabulary).
ADD = "ADD"
NO_OP = "NO_OP"
REQUIRES_RESOLUTION = "REQUIRES_RESOLUTION"
REJECT = "REJECT"

# Closed-vocabulary reason codes.
REASON_ADDED = "ADDED"
REASON_ALREADY_PRESENT = "ALREADY_PRESENT"
REASON_REJECTED_PROPOSAL = "REJECTED_PROPOSAL"
REASON_NOT_CONFIRMED = "NOT_CONFIRMED"
REASON_NO_CONFIRMATION = "NO_CONFIRMATION"
REASON_CONFIRMATION_MISMATCH = "CONFIRMATION_MISMATCH"
REASON_INVALID_EVIDENCE = "INVALID_EVIDENCE"
REASON_UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
REASON_WOULD_OVERWRITE = "WOULD_OVERWRITE_DIFFERENT_VALUE"


@dataclass(frozen=True)
class PromotionDecision:
    """The boundary's verdict: an outcome and a single closed-vocab reason."""

    outcome: str
    reason: str


def promote(
    proposal: FactProposal,
    confirmation: PromotionConfirmation | None,
    current_value: str | None,
    *,
    evidence_valid: bool,
) -> PromotionDecision:
    """Fail-closed decision on whether an imported fact may become trusted.

    Returns ``ADD`` **only** when every condition holds: the proposal is
    ``CONFIRMED``; a confirmation is present and its digest binds the
    proposal's *current* content (recomputed here, so value/source/evidence
    drift and cross-proposal replay all fail); the cited evidence validates
    against its source document; there is no unresolved conflict; and the
    target field currently holds no different trusted value. ``current_value``
    is ``None`` for an absent field, equal for an already-present identical
    value (``NO_OP``), or different (``REQUIRES_RESOLUTION`` -- never a
    silent overwrite). Deterministic; considers no confidence input at all,
    so confidence structurally cannot authorize promotion.
    """
    if proposal.trust_state == TrustState.REJECTED:
        return PromotionDecision(REJECT, REASON_REJECTED_PROPOSAL)
    if proposal.trust_state != TrustState.CONFIRMED:
        return PromotionDecision(REQUIRES_RESOLUTION, REASON_NOT_CONFIRMED)
    if confirmation is None:
        return PromotionDecision(REJECT, REASON_NO_CONFIRMATION)
    expected = compute_binding_digest(proposal)
    if (
        confirmation.confirmation_digest != expected
        or confirmation.proposal_id != proposal.proposal_id
    ):
        return PromotionDecision(REJECT, REASON_CONFIRMATION_MISMATCH)
    if not evidence_valid:
        return PromotionDecision(REJECT, REASON_INVALID_EVIDENCE)
    if proposal.conflict_ids:
        return PromotionDecision(REQUIRES_RESOLUTION, REASON_UNRESOLVED_CONFLICT)
    if current_value is None:
        return PromotionDecision(ADD, REASON_ADDED)
    if current_value == proposal.proposed_value:
        return PromotionDecision(NO_OP, REASON_ALREADY_PRESENT)
    return PromotionDecision(REQUIRES_RESOLUTION, REASON_WOULD_OVERWRITE)


def detect_conflicts(proposals: list[FactProposal]) -> dict[str, list[str]]:
    """Field-local deterministic conflict detection.

    Two proposals conflict iff they target the same **scalar** ``field_path``
    with different ``proposed_value``s -- e.g. two different emails, or a
    graduation year of 2025 vs 2026. This is symmetric and order-independent.
    List-valued fields (``skills``) are never in conflict: two different
    skills are both true. Temporal/employment-overlap reasoning is
    deliberately out of scope (concurrent employment is legitimate, and
    title progression is not a contradiction) -- documented, not silently
    approximated. Returns a mapping of each conflicted proposal_id to the
    sorted ids it conflicts with.
    """
    conflicts: dict[str, set[str]] = {p.proposal_id: set() for p in proposals}
    for i, a in enumerate(proposals):
        if a.field_path in _LIST_FIELDS:
            continue
        for b in proposals[i + 1 :]:
            if (
                a.field_path == b.field_path
                and a.proposed_value != b.proposed_value
            ):
                conflicts[a.proposal_id].add(b.proposal_id)
                conflicts[b.proposal_id].add(a.proposal_id)
    return {pid: sorted(ids) for pid, ids in conflicts.items() if ids}


#: Profile fields that are lists of independently-true items -- never a
#: scalar conflict (two skills do not contradict each other).
_LIST_FIELDS: frozenset[str] = frozenset({"skills"})


class IngestionDraft(BaseModel):
    """The unverified artifact ``import-cv`` writes and ``promote-cv`` reads.

    It is never the profile and never trusted: it is a review surface. The
    user edits ``trust_state`` to ``confirmed`` (or ``rejected``) per
    proposal, then ``promote-cv`` applies the fail-closed boundary. The
    embedded ``binding_digest`` per proposal is what prevents post-import
    tampering (edit a value but not the digest -> mismatch -> refused).
    """

    document_digest: str
    source_type: str
    source_path: str
    proposals: list[FactProposal] = Field(default_factory=list)
