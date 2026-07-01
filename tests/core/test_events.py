"""Tests for career_agent.core.events."""

from __future__ import annotations

import typing
from datetime import UTC, datetime

from career_agent.core.events import (
    ApplicationFailed,
    ApplicationSubmitted,
    ApplicationTierSelected,
    Event,
    HumanActionRequired,
    OpportunityDiscovered,
    OpportunityScored,
    OutcomeRecorded,
    ResumeTailored,
    TruthfulnessRejected,
)

ALL_EVENT_TYPES = [
    OpportunityDiscovered,
    OpportunityScored,
    ResumeTailored,
    TruthfulnessRejected,
    ApplicationTierSelected,
    HumanActionRequired,
    ApplicationSubmitted,
    ApplicationFailed,
    OutcomeRecorded,
]


def _minimal_kwargs(cls: type[Event]) -> dict[str, object]:
    """Build the minimal required kwargs for each concrete event type."""
    common = {"correlation_id": "corr-1"}
    per_type: dict[type[Event], dict[str, object]] = {
        OpportunityDiscovered: {"opportunity_id": "opp-1", "source": "greenhouse"},
        OpportunityScored: {"opportunity_id": "opp-1", "score": 0.8},
        ResumeTailored: {"opportunity_id": "opp-1", "resume_id": "resume-1"},
        TruthfulnessRejected: {"opportunity_id": "opp-1", "rejection_count": 1},
        ApplicationTierSelected: {"application_id": "app-1", "tier": "ats_api"},
        HumanActionRequired: {"application_id": "app-1", "reason": "captcha"},
        ApplicationSubmitted: {"application_id": "app-1", "tier_used": "browser"},
        ApplicationFailed: {
            "application_id": "app-1",
            "tier_attempted": "email",
            "error_category": "smtp_error",
        },
        OutcomeRecorded: {
            "application_id": "app-1",
            "outcome_id": "outcome-1",
            "kind": "interview",
        },
    }
    return {**common, **per_type[cls]}


def test_every_event_type_is_past_tense_and_not_a_command() -> None:
    """Event type names read as facts ("X happened"), never as commands."""
    command_prefixes = ("Do", "Run", "Execute", "Trigger", "Start", "Call")
    for cls in ALL_EVENT_TYPES:
        name = cls.__name__
        assert not name.startswith(command_prefixes), f"{name} reads as a command"


def test_every_event_carries_the_required_envelope_fields() -> None:
    for cls in ALL_EVENT_TYPES:
        event = cls(**_minimal_kwargs(cls))
        assert event.event_id
        assert event.correlation_id == "corr-1"
        assert event.schema_version == 1
        assert isinstance(event.occurred_at, datetime)
        assert event.occurred_at.tzinfo is not None
        assert event.event_type == cls.__name__


def test_event_ids_are_unique_per_instance() -> None:
    a = OpportunityDiscovered(correlation_id="c1", opportunity_id="o1", source="yc")
    b = OpportunityDiscovered(correlation_id="c1", opportunity_id="o1", source="yc")
    assert a.event_id != b.event_id


def test_correlation_id_ties_events_across_the_discover_to_learn_chain() -> None:
    """The same correlation_id must be reusable across every stage of one job."""
    correlation_id = "job-42"
    discovered = OpportunityDiscovered(
        correlation_id=correlation_id, opportunity_id="opp-1", source="lever"
    )
    tailored = ResumeTailored(
        correlation_id=correlation_id, opportunity_id="opp-1", resume_id="resume-1"
    )
    submitted = ApplicationSubmitted(
        correlation_id=correlation_id, application_id="app-1", tier_used="ats_api"
    )
    outcome = OutcomeRecorded(
        correlation_id=correlation_id,
        application_id="app-1",
        outcome_id="outcome-1",
        kind="interview",
    )
    assert (
        discovered.correlation_id
        == tailored.correlation_id
        == submitted.correlation_id
        == outcome.correlation_id
        == correlation_id
    )


def test_event_payloads_reference_entities_by_id_only() -> None:
    """No event payload embeds a whole domain object -- only ID strings."""
    for cls in ALL_EVENT_TYPES:
        for field_name, field in cls.model_fields.items():
            if field_name in {
                "event_type",
                "schema_version",
                "event_id",
                "correlation_id",
                "occurred_at",
            }:
                continue
            annotation = field.annotation
            origin = typing.get_origin(annotation)
            # every non-envelope field must be a primitive (str/int/float), a
            # closed-set Literal (a typed enum of primitives), or a list of
            # primitives -- never a nested BaseModel
            is_primitive = annotation in (str, int, float)
            is_literal_of_primitives = origin is typing.Literal
            is_list_of_primitives = origin is list and typing.get_args(
                annotation
            ) in ((str,), (int,), (float,))
            assert (
                is_primitive or is_literal_of_primitives or is_list_of_primitives
            ), f"{cls.__name__}.{field_name} looks like an embedded object"


def test_now_utc_default_factory_produces_timezone_aware_timestamps() -> None:
    event = Event(event_type="X", correlation_id="c1")
    assert event.occurred_at.tzinfo == UTC
