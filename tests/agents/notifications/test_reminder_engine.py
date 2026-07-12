"""Phase 58 (ADR-0077): ReminderEngine -- reminders computed from real data."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.agents.notifications.reminder_engine import generate_reminders
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.review import ReviewSession
from career_agent.domain.submission import SubmissionResult
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
)


def _application_session(**overrides: object) -> ApplicationSession:
    fields: dict[object, object] = {
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


def _review_session(**overrides: object) -> ReviewSession:
    fields: dict[object, object] = {
        "id": "rev-1",
        "application_session_id": "sess-1",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "provider": "greenhouse",
        "approval_status": "WAITING",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ReviewSession(**fields)


def _submission_result(**overrides: object) -> SubmissionResult:
    fields: dict[object, object] = {
        "id": "sub-1",
        "application_session_id": "sess-1",
        "review_session_id": "rev-1",
        "opportunity_id": "opp-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "submitted": True,
        "status": "SUBMITTED",
    }
    fields.update(overrides)
    return SubmissionResult(**fields)


def _stores(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    return (
        SqliteReviewSessionStore(db),
        SqliteApplicationSessionStore(db),
        SqliteSubmissionResultStore(db),
    )


def test_no_candidates_when_nothing_is_pending(tmp_path: Path) -> None:
    review_store, application_store, submission_store = _stores(tmp_path)
    candidates = generate_reminders(
        "u1",
        review_store=review_store,
        application_store=application_store,
        submission_store=submission_store,
        promptfoo_validated=True,
    )
    assert candidates == []


def test_pending_review_candidate_when_a_review_is_waiting(tmp_path: Path) -> None:
    review_store, application_store, submission_store = _stores(tmp_path)
    review_store.save(_review_session(approval_status="WAITING"), user_id="u1")

    candidates = generate_reminders(
        "u1",
        review_store=review_store,
        application_store=application_store,
        submission_store=submission_store,
        promptfoo_validated=True,
    )
    categories = {c.category for c in candidates}
    assert "reminder_pending_review" in categories


def test_pending_submission_candidate_when_approved_but_not_submitted(
    tmp_path: Path,
) -> None:
    review_store, application_store, submission_store = _stores(tmp_path)
    application_store.save(
        _application_session(status="READY_FOR_REVIEW"), user_id="u1"
    )
    review_store.save(_review_session(approval_status="APPROVED"), user_id="u1")

    candidates = generate_reminders(
        "u1",
        review_store=review_store,
        application_store=application_store,
        submission_store=submission_store,
        promptfoo_validated=True,
    )
    categories = {c.category for c in candidates}
    assert "reminder_pending_submission" in categories


def test_no_pending_submission_candidate_once_actually_submitted(
    tmp_path: Path,
) -> None:
    review_store, application_store, submission_store = _stores(tmp_path)
    application_store.save(
        _application_session(status="READY_FOR_REVIEW"), user_id="u1"
    )
    review_store.save(_review_session(approval_status="APPROVED"), user_id="u1")
    submission_store.save(_submission_result(), user_id="u1")

    candidates = generate_reminders(
        "u1",
        review_store=review_store,
        application_store=application_store,
        submission_store=submission_store,
        promptfoo_validated=True,
    )
    categories = {c.category for c in candidates}
    assert "reminder_pending_submission" not in categories


def test_promptfoo_warning_only_when_not_validated(tmp_path: Path) -> None:
    review_store, application_store, submission_store = _stores(tmp_path)

    validated = generate_reminders(
        "u1",
        review_store=review_store,
        application_store=application_store,
        submission_store=submission_store,
        promptfoo_validated=True,
    )
    assert not any(c.category == "reminder_promptfoo_validation" for c in validated)

    not_validated = generate_reminders(
        "u1",
        review_store=review_store,
        application_store=application_store,
        submission_store=submission_store,
        promptfoo_validated=False,
    )
    warning = next(
        c for c in not_validated if c.category == "reminder_promptfoo_validation"
    )
    assert warning.type == "WARNING"


def test_reminders_are_scoped_to_the_requested_user(tmp_path: Path) -> None:
    review_store, application_store, submission_store = _stores(tmp_path)
    review_store.save(_review_session(approval_status="WAITING"), user_id="u1")

    candidates = generate_reminders(
        "u2",
        review_store=review_store,
        application_store=application_store,
        submission_store=submission_store,
        promptfoo_validated=True,
    )
    assert candidates == []
