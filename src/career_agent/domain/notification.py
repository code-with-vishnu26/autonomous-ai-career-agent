"""Notifications: the dashboard's own event-facing record (Phase 58, ADR-0077).

`user_id` lives in the SQL row, never on this model -- the same
"denormalize identity, not full content" precedent Phase 56's
`SqliteUserStore`-adjacent tables and every `by_user`-scoped store already
established (ADR-0074). A `Notification` is a fact that already happened
("your review was approved"), never a command -- the same past-tense
discipline `core/events.py`'s existing `Event` catalog holds itself to,
applied here to the dashboard's own, separate, persisted record (the
in-process `EventBus` is ephemeral and CLI-only; this is not that bus,
it is what a notification *about* one of those facts looks like once
it needs to survive past one process's lifetime and be shown to a
specific user).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

#: Every notification's severity/kind -- fixed, not open-ended, so a
#: frontend icon/color mapping can be exhaustive.
NotificationType = Literal["INFO", "SUCCESS", "WARNING", "ERROR", "REMINDER", "SYSTEM"]

#: What real event actually produced this notification -- deliberately a
#: fixed, closed set matching only the trigger points that genuinely exist
#: in this codebase today (see ADR-0077's "what this phase does not do"
#: for the event types with no real data source, not included here).
#: ``invitation_received``/``invitation_accepted`` were named-deferred in
#: ADR-0077 ("no invitation system exists") -- Phase 60 (ADR-0078) built
#: one for real, so they are added here as genuinely real triggers now.
NotificationCategory = Literal[
    "resume_prepared",
    "review_approved",
    "review_rejected",
    "submission_completed",
    "submission_cancelled",
    "submission_failed",
    "password_changed",
    "reminder_pending_review",
    "reminder_pending_submission",
    "reminder_promptfoo_validation",
    "digest_daily",
    "digest_weekly",
    "digest_monthly",
    "invitation_received",
    "invitation_accepted",
    "system",
]

#: Delivery status for one channel attempt -- "record actual delivery
#: status, never fabricate success" (this phase's own brief). `SKIPPED`
#: covers "the user disabled this channel" or "no transport configured"
#: -- neither is a failure, but neither is a lie about having sent it.
DeliveryStatus = Literal["SENT", "FAILED", "SKIPPED"]


class Notification(BaseModel):
    """One notification, already generated and stored."""

    id: str
    type: NotificationType
    category: NotificationCategory
    title: str
    message: str
    read_at: datetime | None = None
    created_at: datetime


class DeliveryAttempt(BaseModel):
    """One real attempt to deliver a notification through one channel.

    Persisted so "was this actually emailed" is an answerable question
    from data, not an assumption -- the same "check the evidence" habit
    this project holds everywhere else (``verify_promptfoo_results``,
    ``ClaimVerifier``), applied to delivery claims instead of truthfulness
    claims.
    """

    id: str
    notification_id: str
    channel: Literal["email", "webhook", "browser", "in_app"]
    status: DeliveryStatus
    detail: str = ""
    attempted_at: datetime
