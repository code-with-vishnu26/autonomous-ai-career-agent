"""Phase 51 (ADR-0069): ApplicationSession is pure data, no submission state."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.application_session import ApplicationSession


def _session(**overrides: object) -> ApplicationSession:
    fields = {
        "id": "sess-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "opportunity_id": "opp-1",
        "status": "READY_FOR_REVIEW",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ApplicationSession(**fields)


def test_defaults_are_empty_lists_not_none() -> None:
    session = _session()
    assert session.filled_fields == []
    assert session.detected_fields == []
    assert session.uploaded_files == []
    assert session.missing_fields == []
    assert session.warnings == []
    assert session.resume_variant_id is None
    assert session.cover_letter_body is None


def test_round_trips_through_json() -> None:
    session = _session(
        status="BLOCKED",
        missing_fields=["#custom_question"],
        warnings=["something to review"],
    )
    restored = ApplicationSession.model_validate_json(session.model_dump_json())
    assert restored == session


def test_has_no_field_resembling_a_submission_confirmation() -> None:
    """Structural proof: this type cannot carry a submission outcome at all."""
    field_names = set(ApplicationSession.model_fields)
    for forbidden in ("submitted", "submission_id", "confirmation", "submitted_at"):
        assert forbidden not in field_names
