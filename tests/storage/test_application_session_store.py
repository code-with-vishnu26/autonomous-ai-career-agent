"""Phase 51 (ADR-0069): SqliteApplicationSessionStore -- append-only, same
discipline as SqliteApplicationStore/SqliteResumeVariantStore."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.application_session import ApplicationSession
from career_agent.storage.sqlite import SqliteApplicationSessionStore


def _session(
    id_: str, opportunity_id: str = "opp-1", **overrides: object
) -> ApplicationSession:
    fields = {
        "id": id_,
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "opportunity_id": opportunity_id,
        "status": "READY_FOR_REVIEW",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ApplicationSession(**fields)


def test_save_then_by_opportunity_round_trips(tmp_path: Path) -> None:
    store = SqliteApplicationSessionStore(tmp_path / "db.sqlite")
    session = _session("sess-1")
    store.save(session)
    assert store.by_opportunity("opp-1") == [session]


def test_by_opportunity_only_returns_matching_opportunity(tmp_path: Path) -> None:
    store = SqliteApplicationSessionStore(tmp_path / "db.sqlite")
    store.save(_session("sess-1", opportunity_id="opp-1"))
    store.save(_session("sess-2", opportunity_id="opp-2"))
    assert [s.id for s in store.by_opportunity("opp-1")] == ["sess-1"]
    assert [s.id for s in store.by_opportunity("opp-2")] == ["sess-2"]


def test_by_opportunity_unknown_returns_empty(tmp_path: Path) -> None:
    store = SqliteApplicationSessionStore(tmp_path / "db.sqlite")
    assert store.by_opportunity("nonexistent") == []


def test_save_is_append_only_never_overwrites(tmp_path: Path) -> None:
    store = SqliteApplicationSessionStore(tmp_path / "db.sqlite")
    original = _session("sess-1", status="READY_FOR_REVIEW")
    store.save(original)
    mutated = original.model_copy(update={"status": "BLOCKED"})
    store.save(mutated)
    result = store.by_opportunity("opp-1")
    assert len(result) == 1
    assert result[0].status == "READY_FOR_REVIEW"


def test_all_sessions_returns_every_opportunity(tmp_path: Path) -> None:
    store = SqliteApplicationSessionStore(tmp_path / "db.sqlite")
    store.save(_session("sess-1", opportunity_id="opp-1"))
    store.save(_session("sess-2", opportunity_id="opp-2"))
    ids = {s.id for s in store.all_sessions()}
    assert ids == {"sess-1", "sess-2"}


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    SqliteApplicationSessionStore(path).save(_session("sess-1"))
    reopened = SqliteApplicationSessionStore(path)
    assert [s.id for s in reopened.by_opportunity("opp-1")] == ["sess-1"]
