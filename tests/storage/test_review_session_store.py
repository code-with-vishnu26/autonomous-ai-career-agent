"""Phase 52 (ADR-0070): SqliteReviewSessionStore -- append-only, same
discipline as SqliteApplicationStore/SqliteResumeVariantStore."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.review import ReviewSession
from career_agent.storage.sqlite import SqliteReviewSessionStore


def _review(
    id_: str, application_session_id: str = "sess-1", **overrides: object
) -> ReviewSession:
    fields = {
        "id": id_,
        "application_session_id": application_session_id,
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "provider": "greenhouse",
        "approval_status": "APPROVED",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ReviewSession(**fields)


def test_save_then_by_application_session_round_trips(tmp_path: Path) -> None:
    store = SqliteReviewSessionStore(tmp_path / "db.sqlite")
    review = _review("review-1")
    store.save(review)
    assert store.by_application_session("sess-1") == [review]


def test_by_application_session_only_returns_matching(tmp_path: Path) -> None:
    store = SqliteReviewSessionStore(tmp_path / "db.sqlite")
    store.save(_review("review-1", application_session_id="sess-1"))
    store.save(_review("review-2", application_session_id="sess-2"))
    assert [r.id for r in store.by_application_session("sess-1")] == ["review-1"]
    assert [r.id for r in store.by_application_session("sess-2")] == ["review-2"]


def test_by_application_session_unknown_returns_empty(tmp_path: Path) -> None:
    store = SqliteReviewSessionStore(tmp_path / "db.sqlite")
    assert store.by_application_session("nonexistent") == []


def test_save_is_append_only_never_overwrites(tmp_path: Path) -> None:
    store = SqliteReviewSessionStore(tmp_path / "db.sqlite")
    original = _review("review-1", approval_status="APPROVED")
    store.save(original)
    mutated = original.model_copy(update={"approval_status": "REJECTED"})
    store.save(mutated)
    result = store.by_application_session("sess-1")
    assert len(result) == 1
    assert result[0].approval_status == "APPROVED"


def test_all_reviews_returns_every_application_session(tmp_path: Path) -> None:
    store = SqliteReviewSessionStore(tmp_path / "db.sqlite")
    store.save(_review("review-1", application_session_id="sess-1"))
    store.save(_review("review-2", application_session_id="sess-2"))
    ids = {r.id for r in store.all_reviews()}
    assert ids == {"review-1", "review-2"}


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    SqliteReviewSessionStore(path).save(_review("review-1"))
    reopened = SqliteReviewSessionStore(path)
    assert [r.id for r in reopened.by_application_session("sess-1")] == ["review-1"]


def test_rejected_review_survives_round_trip(tmp_path: Path) -> None:
    store = SqliteReviewSessionStore(tmp_path / "db.sqlite")
    review = _review("review-1", approval_status="REJECTED", review_notes="not a fit")
    store.save(review)
    result = store.by_application_session("sess-1")[0]
    assert result.approval_status == "REJECTED"
    assert result.review_notes == "not a fit"
    assert result.approved_at is None
