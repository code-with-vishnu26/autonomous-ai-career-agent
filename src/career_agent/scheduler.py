"""Background scheduler (Phase 58, ADR-0077).

``AsyncIOScheduler`` (APScheduler), run in-process alongside the FastAPI
event loop (wired into ``api/app.py``'s existing ``lifespan`` hook,
Phase 59) -- no separate worker process, no message queue, matching this
project's existing "one SQLite file, one process, no contention problem
to solve" scale (``storage/sqlite.py``'s own module docstring).

**This module structurally cannot submit anything.** Every job function
here only ever reads existing stores and writes to the notification-
specific stores (``SqliteNotificationStore``/``SqliteDeliveryAttemptStore``);
none imports ``SubmissionEngine``, ``BrowserApplicator``, or any
``integrations.browser`` symbol. Proven by an AST-based source-scan test
(``tests/core/test_scheduler_purity.py``), the same structural-guarantee
discipline ``ApplicationPreparationEngine``'s own no-submit-selector test
and ``ReviewEngine``'s own no-browser-import test already established --
not merely a docstring promise.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from career_agent.agents.notifications.digest_generator import generate_digest
from career_agent.agents.notifications.dispatcher import NotificationDispatcher
from career_agent.agents.notifications.engine import NotificationEngine
from career_agent.agents.notifications.reminder_engine import generate_reminders
from career_agent.agents.notifications.templates import digest_email
from career_agent.core.config import Settings
from career_agent.domain.notification import DeliveryAttempt
from career_agent.integrations.email import EmailSender, SmtpEmailSender
from career_agent.integrations.webhook import WebhookSender
from career_agent.llm.promptfoo_gate import (
    PromptfooNotValidatedError,
    verify_promptfoo_results,
)
from career_agent.llm.providers import (
    NoLLMProviderConfiguredError,
    select_claim_verifier,
)
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteDeliveryAttemptStore,
    SqliteNotificationPreferencesStore,
    SqliteNotificationStore,
    SqlitePasswordResetTokenStore,
    SqliteRefreshTokenStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
    SqliteUserStore,
    SqliteWebhookSubscriptionStore,
)

logger = logging.getLogger(__name__)

#: How recently the same reminder category must have already fired for a
#: user before the reminder job skips it -- avoids re-notifying every
#: single scheduler tick for the same still-ongoing condition (e.g. one
#: review that's been WAITING for three days doesn't need three days'
#: worth of identical reminders).
_REMINDER_COOLDOWN = timedelta(hours=12)


def build_email_sender(settings: Settings) -> EmailSender | None:
    """A real :class:`EmailSender` if SMTP is configured, else ``None``."""
    if not settings.smtp_host or not settings.smtp_from_address:
        return None
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        from_address=settings.smtp_from_address,
    )


def _promptfoo_validated(settings: Settings) -> bool:
    try:
        verifier = select_claim_verifier(settings)
        verify_promptfoo_results(
            verifier.prompt_version,
            Path(settings.promptfoo_results_dir),
            provider_id=verifier.provider_id,
        )
        return True
    except (NoLLMProviderConfiguredError, PromptfooNotValidatedError):
        return False


async def run_reminder_job(settings: Settings) -> None:
    """Compute and dispatch every applicable reminder, for every user."""
    db_path = Path(settings.database_path)
    user_store = SqliteUserStore(db_path)
    review_store = SqliteReviewSessionStore(db_path)
    application_store = SqliteApplicationSessionStore(db_path)
    submission_store = SqliteSubmissionResultStore(db_path)
    notification_store = SqliteNotificationStore(db_path)
    preferences_store = SqliteNotificationPreferencesStore(db_path)
    webhook_store = SqliteWebhookSubscriptionStore(db_path)
    delivery_store = SqliteDeliveryAttemptStore(db_path)

    engine = NotificationEngine(notification_store)
    dispatcher = NotificationDispatcher(
        delivery_store=delivery_store,
        email_sender=build_email_sender(settings),
        webhook_sender=WebhookSender(HttpxClient()),
    )
    promptfoo_validated = _promptfoo_validated(settings)
    now = datetime.now(UTC)

    for user in user_store.all_users():
        preferences = preferences_store.get_or_default(user.id)
        if not preferences.enable_reminders:
            continue
        candidates = generate_reminders(
            user.id,
            review_store=review_store,
            application_store=application_store,
            submission_store=submission_store,
            promptfoo_validated=promptfoo_validated,
        )
        recent = notification_store.by_user(user.id)
        for candidate in candidates:
            already_recent = any(
                notification.category == candidate.category
                and now - notification.created_at < _REMINDER_COOLDOWN
                for notification in recent
            )
            if already_recent:
                continue
            notification = engine.create(
                user_id=user.id,
                type=candidate.type,
                category=candidate.category,
                title=candidate.title,
                message=candidate.message,
                now=now,
            )
            await dispatcher.dispatch(
                notification,
                user_id=user.id,
                preferences=preferences,
                email_address=user.email,
                webhook_url=webhook_store.get(user.id),
                now=now,
            )


async def _run_digest_job(settings: Settings, period: str) -> None:
    db_path = Path(settings.database_path)
    user_store = SqliteUserStore(db_path)
    application_store = SqliteApplicationSessionStore(db_path)
    review_store = SqliteReviewSessionStore(db_path)
    submission_store = SqliteSubmissionResultStore(db_path)
    notification_store = SqliteNotificationStore(db_path)
    preferences_store = SqliteNotificationPreferencesStore(db_path)
    webhook_store = SqliteWebhookSubscriptionStore(db_path)
    delivery_store = SqliteDeliveryAttemptStore(db_path)

    engine = NotificationEngine(notification_store)
    dispatcher = NotificationDispatcher(
        delivery_store=delivery_store,
        email_sender=build_email_sender(settings),
        webhook_sender=WebhookSender(HttpxClient()),
    )
    now = datetime.now(UTC)

    for user in user_store.all_users():
        preferences = preferences_store.get_or_default(user.id)
        if not preferences.enable_digests:
            continue
        summary = generate_digest(
            user.id,
            period,  # type: ignore[arg-type]
            application_store=application_store,
            review_store=review_store,
            submission_store=submission_store,
            now=now,
        )
        subject, _ = digest_email(period=period, summary_lines=summary.as_lines())
        notification = engine.create(
            user_id=user.id,
            type="INFO",
            category=f"digest_{period}",  # type: ignore[arg-type]
            title=subject,
            message="\n".join(summary.as_lines()),
            now=now,
        )
        await dispatcher.dispatch(
            notification,
            user_id=user.id,
            preferences=preferences,
            email_address=user.email,
            webhook_url=webhook_store.get(user.id),
            now=now,
        )


async def run_daily_digest_job(settings: Settings) -> None:
    """Generate + dispatch the daily digest for every user."""
    await _run_digest_job(settings, "daily")


async def run_weekly_digest_job(settings: Settings) -> None:
    """Generate + dispatch the weekly digest for every user."""
    await _run_digest_job(settings, "weekly")


async def run_notification_cleanup_job(settings: Settings) -> None:
    """Delete already-read notifications older than the retention window."""
    db_path = Path(settings.database_path)
    cutoff = datetime.now(UTC) - timedelta(days=settings.notification_retention_days)
    deleted = SqliteNotificationStore(db_path).delete_read_older_than(cutoff=cutoff)
    logger.info("Notification cleanup: deleted %d read notification(s)", deleted)


async def run_expired_token_cleanup_job(settings: Settings) -> None:
    """Delete expired refresh/password-reset tokens (Phase 56 stores, extended here)."""
    db_path = Path(settings.database_path)
    refresh_deleted = SqliteRefreshTokenStore(db_path).delete_expired()
    reset_deleted = SqlitePasswordResetTokenStore(db_path).delete_expired()
    logger.info(
        "Expired token cleanup: %d refresh token(s), %d reset token(s) deleted",
        refresh_deleted,
        reset_deleted,
    )


async def run_retry_failed_webhooks_job(settings: Settings) -> None:
    """Retry the most recent failed webhook delivery per user, once."""
    db_path = Path(settings.database_path)
    user_store = SqliteUserStore(db_path)
    delivery_store = SqliteDeliveryAttemptStore(db_path)
    webhook_store = SqliteWebhookSubscriptionStore(db_path)
    notification_store = SqliteNotificationStore(db_path)
    sender = WebhookSender(HttpxClient())

    for user in user_store.all_users():
        url = webhook_store.get(user.id)
        if not url:
            continue
        failed = delivery_store.failed_webhook_attempts(user_id=user.id)
        if not failed:
            continue
        latest = failed[0]
        notification = notification_store.get(latest.notification_id, user_id=user.id)
        if notification is None:
            continue
        try:
            await sender.send(url=url, notification=notification)
            status, detail = "SENT", ""
        except Exception as exc:  # noqa: BLE001 -- record the retry outcome either way
            status, detail = "FAILED", str(exc)
        delivery_store.save(
            DeliveryAttempt(
                id=str(uuid.uuid4()),
                notification_id=notification.id,
                channel="webhook",
                status=status,  # type: ignore[arg-type]
                detail=detail,
                attempted_at=datetime.now(UTC),
            ),
            user_id=user.id,
        )


class HttpxClient:
    """A minimal, real ``HttpClient`` for the scheduler's webhook sends.

    The same ``httpx`` this project already depends on for every other
    real-network call, no new dependency.
    """

    async def get_json(self, url: str, *, params=None, headers=None) -> object:
        """Not used by the scheduler -- it only ever POSTs webhook payloads."""
        raise NotImplementedError("the scheduler only ever POSTs webhook payloads")

    async def post_json(self, url: str, *, json: dict, headers=None) -> object:
        """POST ``json`` to ``url`` and return the parsed JSON response body."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=json, headers=headers)
            response.raise_for_status()
            return response.json() if response.content else {}


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    """Construct (but do not start) the background scheduler, with every job wired.

    Callers (``api/app.py``'s lifespan hook) start/shut it down explicitly
    -- constructing it here never has a side effect.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_reminder_job,
        "interval",
        minutes=settings.reminder_interval_minutes,
        args=[settings],
        id="reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_digest_job,
        "cron",
        hour=8,
        minute=0,
        args=[settings],
        id="daily_digest",
        replace_existing=True,
    )
    scheduler.add_job(
        run_weekly_digest_job,
        "cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        args=[settings],
        id="weekly_digest",
        replace_existing=True,
    )
    scheduler.add_job(
        run_notification_cleanup_job,
        "interval",
        hours=24,
        args=[settings],
        id="notification_cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        run_expired_token_cleanup_job,
        "interval",
        hours=24,
        args=[settings],
        id="expired_token_cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        run_retry_failed_webhooks_job,
        "interval",
        minutes=15,
        args=[settings],
        id="retry_failed_webhooks",
        replace_existing=True,
    )
    return scheduler
