"""Phase 63 (ADR-0081): SqliteDiscoveryRunStore -- a real upsert (unlike the
append-only stores elsewhere in this file), same idiom as
SqliteUserPreferencesStore since a run transitions in place."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.discovery_run import DiscoveryRun
from career_agent.storage.sqlite import SqliteDiscoveryRunStore


def _run(id_: str, user_id: str = "u1", **overrides: object) -> DiscoveryRun:
    fields = {
        "id": id_,
        "user_id": user_id,
        "status": "PENDING",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return DiscoveryRun(**fields)


def test_save_then_get_round_trips(tmp_path: Path) -> None:
    store = SqliteDiscoveryRunStore(tmp_path / "db.sqlite")
    run = _run("run-1")
    store.save(run)
    assert store.get("run-1", user_id="u1") == run


def test_get_scoped_to_owning_user_only(tmp_path: Path) -> None:
    store = SqliteDiscoveryRunStore(tmp_path / "db.sqlite")
    store.save(_run("run-1", user_id="u1"))
    assert store.get("run-1", user_id="someone-else") is None


def test_get_unknown_returns_none(tmp_path: Path) -> None:
    store = SqliteDiscoveryRunStore(tmp_path / "db.sqlite")
    assert store.get("nonexistent", user_id="u1") is None


def test_save_is_a_real_upsert_not_append_only(tmp_path: Path) -> None:
    """Unlike ReviewSession/ApplicationSession, a run's status genuinely
    changes over its lifecycle (PENDING -> RUNNING -> COMPLETED) -- a
    second save for the same id must overwrite, not create a duplicate."""
    store = SqliteDiscoveryRunStore(tmp_path / "db.sqlite")
    store.save(_run("run-1", status="PENDING"))
    store.save(_run("run-1", status="COMPLETED", new_count=3))
    assert store.get("run-1", user_id="u1").status == "COMPLETED"
    assert store.get("run-1", user_id="u1").new_count == 3
    assert len(store.by_user("u1")) == 1


def test_by_user_returns_only_that_users_runs_newest_first(tmp_path: Path) -> None:
    store = SqliteDiscoveryRunStore(tmp_path / "db.sqlite")
    store.save(_run("run-1", user_id="u1", started_at=datetime(2026, 1, 1, tzinfo=UTC)))
    store.save(_run("run-2", user_id="u1", started_at=datetime(2026, 1, 2, tzinfo=UTC)))
    store.save(_run("run-3", user_id="someone-else"))
    assert [r.id for r in store.by_user("u1")] == ["run-2", "run-1"]


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    SqliteDiscoveryRunStore(path).save(_run("run-1"))
    reopened = SqliteDiscoveryRunStore(path)
    assert reopened.get("run-1", user_id="u1") is not None
