"""Phase 52 (ADR-0070): pure Human Review Center data + deterministic summary."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.review import (
    ReviewResult,
    build_review_session,
    format_review_summary,
)


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


# ---------------------------------------------------------------------------
# format_review_summary: deterministic, hides nothing.
# ---------------------------------------------------------------------------


def test_summary_shows_company_role_provider() -> None:
    summary = format_review_summary(_session())
    assert "Acme Corp" in summary
    assert "Backend Engineer" in summary
    assert "greenhouse" in summary


def test_summary_shows_every_warning() -> None:
    session = _session(warnings=["Unknown salary question", "Custom assessment"])
    summary = format_review_summary(session)
    assert "Unknown salary question" in summary
    assert "Custom assessment" in summary


def test_summary_shows_every_missing_field() -> None:
    session = _session(missing_fields=["Current salary", "Notice period"])
    summary = format_review_summary(session)
    assert "Current salary" in summary
    assert "Notice period" in summary


def test_summary_shows_uploaded_files() -> None:
    session = _session(uploaded_files=["/tmp/resume.docx"])
    summary = format_review_summary(session)
    assert "/tmp/resume.docx" in summary


def test_summary_ready_yes_for_ready_for_review() -> None:
    summary = format_review_summary(_session(status="READY_FOR_REVIEW"))
    assert "YES" in summary


def test_summary_ready_no_for_blocked() -> None:
    summary = format_review_summary(_session(status="BLOCKED"))
    assert "NO" in summary


def test_summary_is_deterministic() -> None:
    session = _session(warnings=["a"], missing_fields=["b"])
    assert format_review_summary(session) == format_review_summary(session)


def test_summary_omits_uploaded_section_when_nothing_uploaded_or_no_cover_letter() -> (
    None
):
    summary = format_review_summary(_session())
    assert "Uploaded" not in summary


# ---------------------------------------------------------------------------
# build_review_session: pure construction, references not duplicates.
# ---------------------------------------------------------------------------


def test_build_review_session_links_to_the_application_session() -> None:
    session = _session()
    result = ReviewResult(
        approved=True,
        status="APPROVED",
        review_time=datetime(2026, 1, 2, tzinfo=UTC),
        next_action="eligible_for_submission_engine",
    )
    review = build_review_session("review-1", session, result)
    assert review.id == "review-1"
    assert review.application_session_id == "sess-1"
    assert review.company == "Acme Corp"
    assert review.job_title == "Backend Engineer"
    assert review.provider == "greenhouse"
    assert review.approval_status == "APPROVED"
    assert review.approved_at == result.review_time


def test_build_review_session_rejected_has_no_approved_at() -> None:
    session = _session()
    result = ReviewResult(
        approved=False,
        status="REJECTED",
        review_time=datetime(2026, 1, 2, tzinfo=UTC),
        next_action="revise_and_re_prepare",
    )
    review = build_review_session("review-1", session, result)
    assert review.approval_status == "REJECTED"
    assert review.approved_at is None


def test_review_session_does_not_duplicate_application_session_content() -> None:
    """Structural proof: no field on ReviewSession can carry a copy of
    warnings/missing_fields/filled_fields/uploaded_files/resume content --
    that data always comes from re-reading the referenced ApplicationSession.
    """
    from career_agent.domain.review import ReviewSession

    field_names = set(ReviewSession.model_fields)
    for forbidden in (
        "warnings",
        "missing_fields",
        "filled_fields",
        "uploaded_files",
        "resume_variant",
        "cover_letter",
    ):
        assert forbidden not in field_names
