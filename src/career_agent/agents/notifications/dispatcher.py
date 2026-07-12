"""NotificationDispatcher: decides which channels to attempt (Phase 58, ADR-0077).

Also records what actually happened. In-app is always recorded ``SENT``
-- the notification's own row already
being in :class:`~career_agent.storage.sqlite.SqliteNotificationStore` (via
``NotificationEngine.create``) *is* the in-app delivery; there is nothing
further to attempt. Email and webhook are only attempted if the user has
the channel enabled, wants this notification's category, isn't in quiet
hours, and has the channel actually configured (an email address /
webhook URL). Every branch records a real
:class:`~career_agent.domain.notification.DeliveryAttempt` -- "record
actual delivery status, never fabricate success" applies to every
possible outcome, not just the happy path.

Browser notifications are deliberately **not** dispatched from here at
all: they are delivered client-side (the frontend polls
``/notifications/unread`` and uses the Browser Notification API itself,
`components/BrowserNotifier.tsx`) -- there is no server-side "send a
browser notification" action to attempt or log.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from career_agent.domain.notification import DeliveryAttempt, Notification
from career_agent.domain.notification_preferences import NotificationPreferences
from career_agent.integrations.email import EmailSender, EmailSendError
from career_agent.integrations.webhook import WebhookDeliveryError, WebhookSender
from career_agent.storage.sqlite import SqliteDeliveryAttemptStore


def _in_quiet_hours(preferences: NotificationPreferences, now: datetime) -> bool:
    """Whether ``now`` falls inside the user's configured quiet hours.

    Both bounds must be set to mean anything -- either alone would be
    ambiguous (quiet from when, until when?). Handles a window that
    wraps past midnight (e.g. 22:00-07:00) by comparing the wrapped case
    separately from the same-day case.
    """
    start = preferences.quiet_hours_start
    end = preferences.quiet_hours_end
    if start is None or end is None:
        return False
    try:
        local_now = now.astimezone(ZoneInfo(preferences.timezone)).time()
    except Exception:  # noqa: BLE001 -- an unknown timezone must never crash dispatch
        local_now = now.astimezone(UTC).time()
    if start <= end:
        return start <= local_now <= end
    return local_now >= start or local_now <= end


class NotificationDispatcher:
    """Attempts real delivery through every enabled, configured channel."""

    def __init__(
        self,
        *,
        delivery_store: SqliteDeliveryAttemptStore,
        email_sender: EmailSender | None,
        webhook_sender: WebhookSender | None,
    ) -> None:
        """Configure with real channel senders (``None`` means unconfigured)."""
        self._delivery_store = delivery_store
        self._email_sender = email_sender
        self._webhook_sender = webhook_sender

    async def dispatch(
        self,
        notification: Notification,
        *,
        user_id: str,
        preferences: NotificationPreferences,
        email_address: str | None,
        webhook_url: str | None,
        now: datetime | None = None,
    ) -> list[DeliveryAttempt]:
        """Attempt every applicable channel; return every real attempt recorded."""
        moment = now or datetime.now(UTC)
        attempts = [
            self._record(notification, user_id, "in_app", "SENT", "stored", moment)
        ]

        if not preferences.wants_category(notification.category):
            return attempts

        quiet = _in_quiet_hours(preferences, moment)

        if preferences.enable_email:
            attempts.append(
                await self._attempt_email(
                    notification, user_id, email_address, quiet, moment
                )
            )
        if webhook_url:
            attempts.append(
                await self._attempt_webhook(
                    notification, user_id, webhook_url, quiet, moment
                )
            )
        return attempts

    async def _attempt_email(
        self,
        notification: Notification,
        user_id: str,
        email_address: str | None,
        quiet: bool,
        moment: datetime,
    ) -> DeliveryAttempt:
        if not email_address:
            return self._record(
                notification,
                user_id,
                "email",
                "SKIPPED",
                "no email address on file",
                moment,
            )
        if self._email_sender is None:
            return self._record(
                notification, user_id, "email", "SKIPPED", "SMTP not configured", moment
            )
        if quiet:
            return self._record(
                notification, user_id, "email", "SKIPPED", "quiet hours", moment
            )
        try:
            await self._email_sender.send(
                to=email_address, subject=notification.title, body=notification.message
            )
        except EmailSendError as exc:
            return self._record(
                notification, user_id, "email", "FAILED", str(exc), moment
            )
        return self._record(notification, user_id, "email", "SENT", "", moment)

    async def _attempt_webhook(
        self,
        notification: Notification,
        user_id: str,
        webhook_url: str,
        quiet: bool,
        moment: datetime,
    ) -> DeliveryAttempt:
        if self._webhook_sender is None:
            return self._record(
                notification,
                user_id,
                "webhook",
                "SKIPPED",
                "no webhook sender configured",
                moment,
            )
        if quiet:
            return self._record(
                notification, user_id, "webhook", "SKIPPED", "quiet hours", moment
            )
        try:
            await self._webhook_sender.send(url=webhook_url, notification=notification)
        except WebhookDeliveryError as exc:
            return self._record(
                notification, user_id, "webhook", "FAILED", str(exc), moment
            )
        return self._record(notification, user_id, "webhook", "SENT", "", moment)

    def _record(
        self,
        notification: Notification,
        user_id: str,
        channel: str,
        status: str,
        detail: str,
        moment: datetime,
    ) -> DeliveryAttempt:
        attempt = DeliveryAttempt(
            id=str(uuid.uuid4()),
            notification_id=notification.id,
            channel=channel,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            detail=detail,
            attempted_at=moment,
        )
        self._delivery_store.save(attempt, user_id=user_id)
        return attempt
