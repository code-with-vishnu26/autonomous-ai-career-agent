"""Phase 53 (ADR-0071): SubmissionResult is pure data."""

from __future__ import annotations

from career_agent.domain.submission import SubmissionResult


def _result(**overrides: object) -> SubmissionResult:
    fields = {
        "id": "sub-1",
        "application_session_id": "sess-1",
        "review_session_id": "review-1",
        "opportunity_id": "opp-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "submitted": False,
        "status": "REFUSED",
    }
    fields.update(overrides)
    return SubmissionResult(**fields)


def test_defaults_are_empty_not_none() -> None:
    result = _result()
    assert result.warnings == []
    assert result.confirmation_id is None
    assert result.confirmation_url is None
    assert result.submitted_at is None


def test_round_trips_through_json() -> None:
    result = _result(
        status="SUBMITTED",
        submitted=True,
        warnings=["no verified confirmation-id selector"],
    )
    restored = SubmissionResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_every_status_value_is_constructible() -> None:
    for status in ("SUBMITTED", "FAILED", "UNKNOWN", "ABORTED", "CANCELLED", "REFUSED"):
        result = _result(status=status)
        assert result.status == status
