"""Phase 60 (ADR-0078): SqliteAuditLogStore -- append-only."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.audit import AuditLogEntry
from career_agent.storage.audit_store import SqliteAuditLogStore

_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _entry(**overrides: object) -> AuditLogEntry:
    fields: dict[object, object] = {
        "id": "a1",
        "organization_id": "o1",
        "user_id": "u1",
        "action": "organization_created",
        "result": "ok",
        "created_at": _FIXED_NOW,
    }
    fields.update(overrides)
    return AuditLogEntry(**fields)


def test_record_and_by_organization(tmp_path: Path) -> None:
    store = SqliteAuditLogStore(tmp_path / "db.sqlite")
    store.record(_entry())
    assert store.by_organization("o1") == [_entry()]


def test_by_organization_scoped_to_organization(tmp_path: Path) -> None:
    store = SqliteAuditLogStore(tmp_path / "db.sqlite")
    store.record(_entry(id="a1", organization_id="o1"))
    store.record(_entry(id="a2", organization_id="o2"))
    assert [e.id for e in store.by_organization("o1")] == ["a1"]


def test_by_organization_newest_first(tmp_path: Path) -> None:
    store = SqliteAuditLogStore(tmp_path / "db.sqlite")
    older = datetime(2020, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 1, 1, tzinfo=UTC)
    store.record(_entry(id="old", created_at=older))
    store.record(_entry(id="new", created_at=newer))
    assert [e.id for e in store.by_organization("o1")] == ["new", "old"]


def test_by_organization_respects_limit(tmp_path: Path) -> None:
    store = SqliteAuditLogStore(tmp_path / "db.sqlite")
    for i in range(5):
        store.record(_entry(id=f"a{i}"))
    assert len(store.by_organization("o1", limit=2)) == 2
