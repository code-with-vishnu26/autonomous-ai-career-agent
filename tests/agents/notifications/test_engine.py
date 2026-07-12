"""Phase 58 (ADR-0077): NotificationEngine."""

from __future__ import annotations

from pathlib import Path

from career_agent.agents.notifications.engine import NotificationEngine
from career_agent.storage.sqlite import SqliteNotificationStore


def test_create_persists_and_returns_the_notification(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    engine = NotificationEngine(store)

    notification = engine.create(
        user_id="u1",
        type="SUCCESS",
        category="resume_prepared",
        title="Prepared",
        message="Ready for review.",
    )

    assert notification.title == "Prepared"
    assert notification.read_at is None
    stored = store.by_user("u1")
    assert [n.id for n in stored] == [notification.id]


def test_create_generates_a_unique_id_per_call(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    engine = NotificationEngine(store)
    first = engine.create(
        user_id="u1", type="INFO", category="system", title="a", message="a"
    )
    second = engine.create(
        user_id="u1", type="INFO", category="system", title="b", message="b"
    )
    assert first.id != second.id
