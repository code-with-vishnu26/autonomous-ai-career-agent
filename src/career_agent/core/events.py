"""Event catalog: the only channel agents use to communicate (ADR-0005).

Every event is a past-tense fact ("X happened"), never a command ("do X") --
that is what keeps this a true event bus instead of a disguised set of
function calls. Payloads reference domain entities by ID only; the entities
themselves live in storage and are fetched by ID, never embedded in the
event. If a payload ever needs more than a handful of fields, that is a sign
two agents have become secretly coupled through the event, not a sign the
event needs a bigger payload.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def _event_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Event(BaseModel):
    """Base envelope every event carries, regardless of type.

    ``correlation_id`` ties one opportunity's Discover -> Decide -> Apply ->
    Learn chain together across every event it produces, so the whole chain
    can be traced end to end. ``schema_version`` lets an event's payload
    shape evolve without silently breaking older subscribers.
    """

    event_type: str
    schema_version: int = 1
    event_id: str = Field(default_factory=_event_id)
    correlation_id: str
    occurred_at: datetime = Field(default_factory=_now)


class OpportunityDiscovered(Event):
    """A new opportunity was found by a Discovery source."""

    event_type: str = "OpportunityDiscovered"
    opportunity_id: str
    source: str


class OpportunityScored(Event):
    """The Planner's scoring step ranked an opportunity."""

    event_type: str = "OpportunityScored"
    opportunity_id: str
    score: float
    reasons: list[str] = Field(default_factory=list)


class ResumeTailored(Event):
    """A draft was generated and passed the truthfulness gate."""

    event_type: str = "ResumeTailored"
    opportunity_id: str
    resume_id: str


class TruthfulnessRejected(Event):
    """The gate blocked a draft (ADR-0003) -- a hard stop, not a warning."""

    event_type: str = "TruthfulnessRejected"
    opportunity_id: str
    rejection_count: int


class ApplicationTierSelected(Event):
    """The applicator chose which tier to attempt (ADR-0010)."""

    event_type: str = "ApplicationTierSelected"
    application_id: str
    tier: Literal["ats_api", "browser", "email"]


class HumanActionRequired(Event):
    """A supervised pause point (ADR-0008): the human must act to continue.

    ``"fields_need_human_input"`` (Phase 8k, ADR-0032) is BrowserApplicator's
    Phase A pause -- one or more required fields (EEOC, subjective, a
    missing legal-status fact, or anything else this slice doesn't
    auto-resolve) need the human to fill them directly on the live page.
    Distinct from ``"verification"`` (Phase B, a CAPTCHA/challenge wall
    encountered *after* the submit click): Phase A always precedes Phase B.
    """

    event_type: str = "HumanActionRequired"
    application_id: str
    reason: Literal[
        "captcha", "verification", "login", "confirmation", "fields_need_human_input"
    ]


class ApplicationSubmitted(Event):
    """An application was successfully submitted through some tier (ADR-0010)."""

    event_type: str = "ApplicationSubmitted"
    application_id: str
    tier_used: Literal["ats_api", "browser", "email"]


class ApplicationFailed(Event):
    """An application attempt failed at the given tier."""

    event_type: str = "ApplicationFailed"
    application_id: str
    tier_attempted: str
    error_category: str


class OutcomeRecorded(Event):
    """An outcome was recorded for an application (ADR-0009)."""

    event_type: str = "OutcomeRecorded"
    application_id: str
    outcome_id: str
    kind: str


class CandidateHeld(Event):
    """A freeform source held a candidate instead of emitting it (ADR-0013).

    Puts the discovery discard pile on the event bus (the visibility spine) so
    a dashboard or the Learning engine can see what was held and why, rather
    than it vanishing. ``reference`` points back to the raw item held.
    """

    event_type: str = "CandidateHeld"
    source: str
    reason: str
    reference: str
    extraction_confidence: float
