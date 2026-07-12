"""Phase 58 (ADR-0077): scheduler job behavior (not just structural purity).

``tests/test_scheduler_purity.py`` proves the scheduler can never submit
anything; this file proves each job actually does what it claims against
real stores.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from career_agent import scheduler as scheduler_module
from career_agent.core.config import Settings
from career_agent.domain.notification import DeliveryAttempt
from career_agent.domain.notification_preferences import NotificationPreferences
from career_agent.domain.review import ReviewSession
from career_agent.domain.user import User
from career_agent.storage.sqlite import (
    SqliteDeliveryAttemptStore,
    SqliteNotificationPreferencesStore,
    SqliteNotificationStore,
    SqlitePasswordResetTokenStore,
    SqliteRefreshTokenStore,
    SqliteReviewSessionStore,
    SqliteUserStore,
    SqliteWebhookSubscriptionStore,
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    fields: dict[object, object] = {
        "database_path": str(tmp_path / "db.sqlite"),
        "reminder_interval_minutes": 60,
        "notification_retention_days": 30,
    }
    fields.update(overrides)
    return Settings(**fields)


def _create_user(settings: Settings, *, email: str = "user@example.com") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        hashed_password="not-a-real-hash",
        created_at=datetime.now(UTC),
    )
    SqliteUserStore(Path(settings.database_path)).create(user)
    return user


async def test_reminder_job_creates_a_notification_for_a_pending_review(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    user = _create_user(settings)
    review_store = SqliteReviewSessionStore(Path(settings.database_path))
    review_store.save(
        ReviewSession(
            id="rev-1",
            application_session_id="sess-1",
            company="Acme",
            job_title="Backend Engineer",
            provider="greenhouse",
            approval_status="WAITING",
            created_at=datetime.now(UTC),
        ),
        user_id=user.id,
    )

    await scheduler_module.run_reminder_job(settings)

    notifications = SqliteNotificationStore(Path(settings.database_path)).by_user(
        user.id
    )
    assert any(n.category == "reminder_pending_review" for n in notifications)


async def test_reminder_job_skips_users_who_disabled_reminders(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    user = _create_user(settings)
    db_path = Path(settings.database_path)
    SqliteNotificationPreferencesStore(db_path).save(
        user.id, NotificationPreferences(enable_reminders=False)
    )
    SqliteReviewSessionStore(db_path).save(
        ReviewSession(
            id="rev-1",
            application_session_id="sess-1",
            company="Acme",
            job_title="Backend Engineer",
            provider="greenhouse",
            approval_status="WAITING",
            created_at=datetime.now(UTC),
        ),
        user_id=user.id,
    )

    await scheduler_module.run_reminder_job(settings)

    notifications = SqliteNotificationStore(db_path).by_user(user.id)
    assert notifications == []


async def test_reminder_job_does_not_repeat_within_the_cooldown(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    user = _create_user(settings)
    db_path = Path(settings.database_path)
    SqliteReviewSessionStore(db_path).save(
        ReviewSession(
            id="rev-1",
            application_session_id="sess-1",
            company="Acme",
            job_title="Backend Engineer",
            provider="greenhouse",
            approval_status="WAITING",
            created_at=datetime.now(UTC),
        ),
        user_id=user.id,
    )

    await scheduler_module.run_reminder_job(settings)
    await scheduler_module.run_reminder_job(settings)

    notifications = SqliteNotificationStore(db_path).by_user(user.id)
    pending_review = [
        n for n in notifications if n.category == "reminder_pending_review"
    ]
    assert len(pending_review) == 1


async def test_notification_cleanup_job_deletes_only_old_read_notifications(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, notification_retention_days=1)
    user = _create_user(settings)
    db_path = Path(settings.database_path)
    store = SqliteNotificationStore(db_path)

    from career_agent.agents.notifications.engine import NotificationEngine

    engine = NotificationEngine(store)
    old = engine.create(
        user_id=user.id,
        type="INFO",
        category="system",
        title="old",
        message="old",
        now=datetime.now(UTC) - timedelta(days=5),
    )
    recent = engine.create(
        user_id=user.id,
        type="INFO",
        category="system",
        title="recent",
        message="recent",
    )
    store.mark_read(old.id, user_id=user.id, read_at=datetime.now(UTC))
    store.mark_read(recent.id, user_id=user.id, read_at=datetime.now(UTC))

    await scheduler_module.run_notification_cleanup_job(settings)

    remaining_ids = {n.id for n in store.by_user(user.id)}
    assert remaining_ids == {recent.id}


async def test_expired_token_cleanup_job_deletes_expired_tokens(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    db_path = Path(settings.database_path)
    refresh_store = SqliteRefreshTokenStore(db_path)
    reset_store = SqlitePasswordResetTokenStore(db_path)
    user = _create_user(settings)

    refresh_store.save(
        token_id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash="hash1",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    reset_store.save(
        token_id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash="hash2",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    await scheduler_module.run_expired_token_cleanup_job(settings)

    assert refresh_store.delete_expired() == 0
    assert reset_store.delete_expired() == 0


async def test_retry_failed_webhooks_job_retries_the_latest_failure(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    user = _create_user(settings)
    db_path = Path(settings.database_path)

    from career_agent.agents.notifications.engine import NotificationEngine

    notification = NotificationEngine(SqliteNotificationStore(db_path)).create(
        user_id=user.id,
        type="INFO",
        category="system",
        title="t",
        message="m",
    )
    SqliteDeliveryAttemptStore(db_path).save(
        DeliveryAttempt(
            id=str(uuid.uuid4()),
            notification_id=notification.id,
            channel="webhook",
            status="FAILED",
            detail="unreachable",
            attempted_at=datetime.now(UTC),
        ),
        user_id=user.id,
    )
    SqliteWebhookSubscriptionStore(db_path).save(
        user.id, "https://hooks.example.com/x"
    )

    class _AlwaysFailsSender:
        async def send(self, *, url, notification):
            raise RuntimeError("still unreachable")

    monkeypatch_target = scheduler_module.WebhookSender
    scheduler_module.WebhookSender = lambda client: _AlwaysFailsSender()  # type: ignore[assignment]
    try:
        await scheduler_module.run_retry_failed_webhooks_job(settings)
    finally:
        scheduler_module.WebhookSender = monkeypatch_target

    attempts = SqliteDeliveryAttemptStore(db_path).failed_webhook_attempts(
        user_id=user.id
    )
    assert len(attempts) == 2


def test_build_email_sender_returns_none_when_smtp_not_configured(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    assert scheduler_module.build_email_sender(settings) is None


def test_build_email_sender_returns_a_sender_when_configured(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        smtp_host="smtp.example.com",
        smtp_from_address="noreply@example.com",
    )
    assert scheduler_module.build_email_sender(settings) is not None


def test_build_scheduler_wires_exactly_the_six_named_jobs(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    scheduler = scheduler_module.build_scheduler(settings)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {
        "reminders",
        "daily_digest",
        "weekly_digest",
        "notification_cleanup",
        "expired_token_cleanup",
        "retry_failed_webhooks",
    }
