"""Phase 58 (ADR-0077): DigestGenerator -- summaries from real counts only."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.agents.notifications.digest_generator import generate_digest
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
        SqliteApplicationSessionStore(db),
        SqliteReviewSessionStore(db),
        SqliteSubmissionResultStore(db),
    )


def test_empty_digest_is_all_zeros(tmp_path: Path) -> None:
    application_store, review_store, submission_store = _stores(tmp_path)
    summary = generate_digest(
        "u1",
        "daily",
        application_store=application_store,
        review_store=review_store,
        submission_store=submission_store,
        now=datetime.now(UTC),
    )
    assert (summary.prepared, summary.awaiting_review, summary.submitted) == (0, 0, 0)


def test_counts_reflect_stored_data(tmp_path: Path) -> None:
    application_store, review_store, submission_store = _stores(tmp_path)
    now = datetime.now(UTC)
    application_store.save(_application_session(created_at=now), user_id="u1")
    review_store.save(_review_session(approval_status="WAITING"), user_id="u1")
    submission_store.save(_submission_result(submitted_at=now), user_id="u1")

    summary = generate_digest(
        "u1",
        "daily",
        application_store=application_store,
        review_store=review_store,
        submission_store=submission_store,
        now=now,
    )
    assert summary.prepared == 1
    assert summary.awaiting_review == 1
    assert summary.submitted == 1


def test_prepared_outside_the_period_window_is_excluded(tmp_path: Path) -> None:
    application_store, review_store, submission_store = _stores(tmp_path)
    now = datetime.now(UTC)
    long_ago = datetime(2020, 1, 1, tzinfo=UTC)
    application_store.save(_application_session(created_at=long_ago), user_id="u1")

    summary = generate_digest(
        "u1",
        "daily",
        application_store=application_store,
        review_store=review_store,
        submission_store=submission_store,
        now=now,
    )
    assert summary.prepared == 0


def test_submitted_without_submitted_at_is_never_counted(tmp_path: Path) -> None:
    application_store, review_store, submission_store = _stores(tmp_path)
    now = datetime.now(UTC)
    submission_store.save(_submission_result(submitted_at=None), user_id="u1")

    summary = generate_digest(
        "u1",
        "daily",
        application_store=application_store,
        review_store=review_store,
        submission_store=submission_store,
        now=now,
    )
    assert summary.submitted == 0


def test_weekly_window_includes_something_a_daily_window_would_miss(
    tmp_path: Path,
) -> None:
    application_store, review_store, submission_store = _stores(tmp_path)
    now = datetime.now(UTC)
    from datetime import timedelta

    three_days_ago = now - timedelta(days=3)
    application_store.save(
        _application_session(created_at=three_days_ago), user_id="u1"
    )

    daily = generate_digest(
        "u1",
        "daily",
        application_store=application_store,
        review_store=review_store,
        submission_store=submission_store,
        now=now,
    )
    weekly = generate_digest(
        "u1",
        "weekly",
        application_store=application_store,
        review_store=review_store,
        submission_store=submission_store,
        now=now,
    )
    assert daily.prepared == 0
    assert weekly.prepared == 1


def test_as_lines_reports_prepared_awaiting_submitted() -> None:
    from career_agent.agents.notifications.digest_generator import DigestSummary

    summary = DigestSummary(period="daily", prepared=4, awaiting_review=2, submitted=1)
    lines = summary.as_lines()
    assert lines == [
        "4 application(s) prepared",
        "2 awaiting review",
        "1 submitted",
    ]
