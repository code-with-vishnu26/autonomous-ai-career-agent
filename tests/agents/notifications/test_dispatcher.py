"""Phase 58 (ADR-0077): NotificationDispatcher -- real attempts, real recording."""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path

from career_agent.agents.notifications.dispatcher import NotificationDispatcher
from career_agent.domain.notification import Notification
from career_agent.domain.notification_preferences import NotificationPreferences
from career_agent.integrations.email import EmailSendError
from career_agent.integrations.webhook import WebhookDeliveryError
from career_agent.storage.sqlite import SqliteDeliveryAttemptStore


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


class _FakeEmailSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        if self.fail:
            raise EmailSendError("SMTP down")
        self.sent.append((to, subject, body))


class _FakeWebhookSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, Notification]] = []

    async def send(self, *, url: str, notification: Notification) -> None:
        if self.fail:
            raise WebhookDeliveryError("webhook unreachable")
        self.sent.append((url, notification))


def _dispatcher(
    tmp_path: Path, *, email_sender=None, webhook_sender=None
) -> NotificationDispatcher:
    return NotificationDispatcher(
        delivery_store=SqliteDeliveryAttemptStore(tmp_path / "db.sqlite"),
        email_sender=email_sender,
        webhook_sender=webhook_sender,
    )


async def test_in_app_is_always_recorded_sent(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(),
        email_address=None,
        webhook_url=None,
    )
    in_app = next(a for a in attempts if a.channel == "in_app")
    assert in_app.status == "SENT"


async def test_email_skipped_when_disabled(tmp_path: Path) -> None:
    sender = _FakeEmailSender()
    dispatcher = _dispatcher(tmp_path, email_sender=sender)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(enable_email=False),
        email_address="user@example.com",
        webhook_url=None,
    )
    assert not any(a.channel == "email" for a in attempts)
    assert sender.sent == []


async def test_email_skipped_when_no_address_on_file(tmp_path: Path) -> None:
    sender = _FakeEmailSender()
    dispatcher = _dispatcher(tmp_path, email_sender=sender)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(enable_email=True),
        email_address=None,
        webhook_url=None,
    )
    email_attempt = next(a for a in attempts if a.channel == "email")
    assert email_attempt.status == "SKIPPED"
    assert "email address" in email_attempt.detail


async def test_email_skipped_when_sender_not_configured(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path, email_sender=None)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(enable_email=True),
        email_address="user@example.com",
        webhook_url=None,
    )
    email_attempt = next(a for a in attempts if a.channel == "email")
    assert email_attempt.status == "SKIPPED"
    assert "not configured" in email_attempt.detail


async def test_email_sent_records_sent_and_actually_calls_sender(
    tmp_path: Path,
) -> None:
    sender = _FakeEmailSender()
    dispatcher = _dispatcher(tmp_path, email_sender=sender)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(enable_email=True),
        email_address="user@example.com",
        webhook_url=None,
    )
    email_attempt = next(a for a in attempts if a.channel == "email")
    assert email_attempt.status == "SENT"
    assert sender.sent[0][0] == "user@example.com"


async def test_email_failure_is_recorded_failed_never_fabricated_sent(
    tmp_path: Path,
) -> None:
    sender = _FakeEmailSender(fail=True)
    dispatcher = _dispatcher(tmp_path, email_sender=sender)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(enable_email=True),
        email_address="user@example.com",
        webhook_url=None,
    )
    email_attempt = next(a for a in attempts if a.channel == "email")
    assert email_attempt.status == "FAILED"
    assert "SMTP down" in email_attempt.detail


async def test_webhook_only_attempted_when_url_present(tmp_path: Path) -> None:
    sender = _FakeWebhookSender()
    dispatcher = _dispatcher(tmp_path, webhook_sender=sender)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(),
        email_address=None,
        webhook_url=None,
    )
    assert not any(a.channel == "webhook" for a in attempts)


async def test_webhook_sent_when_url_present(tmp_path: Path) -> None:
    sender = _FakeWebhookSender()
    dispatcher = _dispatcher(tmp_path, webhook_sender=sender)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(),
        email_address=None,
        webhook_url="https://hooks.example.com/x",
    )
    webhook_attempt = next(a for a in attempts if a.channel == "webhook")
    assert webhook_attempt.status == "SENT"
    assert sender.sent[0][0] == "https://hooks.example.com/x"


async def test_webhook_failure_is_recorded_failed(tmp_path: Path) -> None:
    sender = _FakeWebhookSender(fail=True)
    dispatcher = _dispatcher(tmp_path, webhook_sender=sender)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=NotificationPreferences(),
        email_address=None,
        webhook_url="https://hooks.example.com/x",
    )
    webhook_attempt = next(a for a in attempts if a.channel == "webhook")
    assert webhook_attempt.status == "FAILED"


async def test_category_not_wanted_skips_every_external_channel(
    tmp_path: Path,
) -> None:
    email_sender = _FakeEmailSender()
    webhook_sender = _FakeWebhookSender()
    dispatcher = _dispatcher(
        tmp_path, email_sender=email_sender, webhook_sender=webhook_sender
    )
    preferences = NotificationPreferences(
        enable_email=True, categories=["review_approved"]
    )
    attempts = await dispatcher.dispatch(
        _notification(category="resume_prepared"),
        user_id="u1",
        preferences=preferences,
        email_address="user@example.com",
        webhook_url="https://hooks.example.com/x",
    )
    channels = {a.channel for a in attempts}
    assert channels == {"in_app"}
    assert email_sender.sent == []
    assert webhook_sender.sent == []


async def test_quiet_hours_skip_email_and_webhook_but_not_in_app(
    tmp_path: Path,
) -> None:
    email_sender = _FakeEmailSender()
    webhook_sender = _FakeWebhookSender()
    dispatcher = _dispatcher(
        tmp_path, email_sender=email_sender, webhook_sender=webhook_sender
    )
    preferences = NotificationPreferences(
        enable_email=True,
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(23, 59),
        timezone="UTC",
    )
    moment = datetime(2026, 1, 1, 22, 30, tzinfo=UTC)
    attempts = await dispatcher.dispatch(
        _notification(),
        user_id="u1",
        preferences=preferences,
        email_address="user@example.com",
        webhook_url="https://hooks.example.com/x",
        now=moment,
    )
    by_channel = {a.channel: a for a in attempts}
    assert by_channel["in_app"].status == "SENT"
    assert by_channel["email"].status == "SKIPPED"
    assert by_channel["webhook"].status == "SKIPPED"
    assert email_sender.sent == []
    assert webhook_sender.sent == []


async def test_delivery_attempts_are_actually_persisted(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    store = SqliteDeliveryAttemptStore(db_path)
    dispatcher = NotificationDispatcher(
        delivery_store=store, email_sender=None, webhook_sender=None
    )
    notification = _notification()
    await dispatcher.dispatch(
        notification,
        user_id="u1",
        preferences=NotificationPreferences(),
        email_address=None,
        webhook_url=None,
    )
    persisted = store.by_notification(notification.id)
    assert len(persisted) == 1
    assert persisted[0].channel == "in_app"
