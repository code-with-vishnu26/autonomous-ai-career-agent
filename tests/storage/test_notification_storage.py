"""Phase 58 (ADR-0077): notification-related SQLite stores."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.notification import DeliveryAttempt, Notification
from career_agent.domain.notification_preferences import NotificationPreferences
from career_agent.storage.sqlite import (
    SqliteDeliveryAttemptStore,
    SqliteNotificationPreferencesStore,
    SqliteNotificationStore,
    SqliteWebhookSubscriptionStore,
)


def _notification(**overrides: object) -> Notification:
    fields: dict[object, object] = {
        "id": "n1",
        "type": "SUCCESS",
        "category": "resume_prepared",
        "title": "Prepared",
        "message": "Ready for review.",
        "created_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return Notification(**fields)


def test_save_and_by_user_round_trips(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    store.save(_notification(), user_id="u1")
    assert [n.id for n in store.by_user("u1")] == ["n1"]


def test_by_user_never_returns_another_users_notifications(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    store.save(_notification(id="n1"), user_id="u1")
    store.save(_notification(id="n2"), user_id="u2")
    assert [n.id for n in store.by_user("u1")] == ["n1"]
    assert [n.id for n in store.by_user("u2")] == ["n2"]


def test_by_user_orders_newest_first(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 6, 1, tzinfo=UTC)
    store.save(_notification(id="old", created_at=older), user_id="u1")
    store.save(_notification(id="new", created_at=newer), user_id="u1")
    assert [n.id for n in store.by_user("u1")] == ["new", "old"]


def test_unread_by_user_excludes_read_notifications(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    store.save(_notification(id="n1"), user_id="u1")
    store.save(_notification(id="n2"), user_id="u1")
    store.mark_read("n1", user_id="u1", read_at=datetime.now(UTC))
    assert [n.id for n in store.unread_by_user("u1")] == ["n2"]


def test_get_returns_none_for_wrong_user(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    store.save(_notification(), user_id="u1")
    assert store.get("n1", user_id="u2") is None
    assert store.get("n1", user_id="u1") is not None


def test_mark_read_returns_false_for_unknown_notification(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    assert store.mark_read("missing", user_id="u1", read_at=datetime.now(UTC)) is False


def test_mark_all_read_marks_only_that_users_unread(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    store.save(_notification(id="n1"), user_id="u1")
    store.save(_notification(id="n2"), user_id="u1")
    store.save(_notification(id="n3"), user_id="u2")
    marked = store.mark_all_read(user_id="u1", read_at=datetime.now(UTC))
    assert marked == 2
    assert store.unread_by_user("u1") == []
    assert len(store.unread_by_user("u2")) == 1


def test_delete_only_removes_the_owning_users_notification(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    store.save(_notification(), user_id="u1")
    assert store.delete("n1", user_id="u2") is False
    assert store.delete("n1", user_id="u1") is True
    assert store.by_user("u1") == []


def test_delete_read_older_than_only_deletes_read_and_old(tmp_path: Path) -> None:
    store = SqliteNotificationStore(tmp_path / "db.sqlite")
    old = datetime(2020, 1, 1, tzinfo=UTC)
    recent = datetime.now(UTC)
    store.save(_notification(id="old-read", created_at=old), user_id="u1")
    store.save(_notification(id="old-unread", created_at=old), user_id="u1")
    store.save(_notification(id="recent-read", created_at=recent), user_id="u1")
    store.mark_read("old-read", user_id="u1", read_at=old)
    store.mark_read("recent-read", user_id="u1", read_at=recent)

    cutoff = datetime(2021, 1, 1, tzinfo=UTC)
    deleted = store.delete_read_older_than(cutoff=cutoff)

    assert deleted == 1
    remaining_ids = {n.id for n in store.by_user("u1")}
    assert remaining_ids == {"old-unread", "recent-read"}


def test_preferences_get_returns_none_before_save(tmp_path: Path) -> None:
    store = SqliteNotificationPreferencesStore(tmp_path / "db.sqlite")
    assert store.get("u1") is None
    assert store.get_or_default("u1") == NotificationPreferences()


def test_preferences_save_and_get_round_trip(tmp_path: Path) -> None:
    store = SqliteNotificationPreferencesStore(tmp_path / "db.sqlite")
    preferences = NotificationPreferences(enable_email=True, enable_digests=False)
    store.save("u1", preferences)
    assert store.get("u1") == preferences


def test_preferences_save_upserts(tmp_path: Path) -> None:
    store = SqliteNotificationPreferencesStore(tmp_path / "db.sqlite")
    store.save("u1", NotificationPreferences(enable_email=True))
    store.save("u1", NotificationPreferences(enable_email=False))
    assert store.get("u1").enable_email is False


def test_delivery_attempt_save_and_by_notification(tmp_path: Path) -> None:
    store = SqliteDeliveryAttemptStore(tmp_path / "db.sqlite")
    store.save(
        DeliveryAttempt(
            id="d1",
            notification_id="n1",
            channel="email",
            status="SENT",
            attempted_at=datetime.now(UTC),
        ),
        user_id="u1",
    )
    attempts = store.by_notification("n1")
    assert len(attempts) == 1
    assert attempts[0].channel == "email"


def test_failed_webhook_attempts_only_returns_failed_webhook_channel(
    tmp_path: Path,
) -> None:
    store = SqliteDeliveryAttemptStore(tmp_path / "db.sqlite")
    store.save(
        DeliveryAttempt(
            id="d1",
            notification_id="n1",
            channel="webhook",
            status="FAILED",
            attempted_at=datetime.now(UTC),
        ),
        user_id="u1",
    )
    store.save(
        DeliveryAttempt(
            id="d2",
            notification_id="n1",
            channel="webhook",
            status="SENT",
            attempted_at=datetime.now(UTC),
        ),
        user_id="u1",
    )
    store.save(
        DeliveryAttempt(
            id="d3",
            notification_id="n1",
            channel="email",
            status="FAILED",
            attempted_at=datetime.now(UTC),
        ),
        user_id="u1",
    )
    failed = store.failed_webhook_attempts(user_id="u1")
    assert [a.id for a in failed] == ["d1"]


def test_webhook_subscription_save_get_delete(tmp_path: Path) -> None:
    store = SqliteWebhookSubscriptionStore(tmp_path / "db.sqlite")
    assert store.get("u1") is None
    store.save("u1", "https://hooks.example.com/x")
    assert store.get("u1") == "https://hooks.example.com/x"
    store.delete("u1")
    assert store.get("u1") is None
