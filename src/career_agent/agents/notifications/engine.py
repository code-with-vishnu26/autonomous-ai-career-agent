"""NotificationEngine: creates and persists one notification (Phase 58, ADR-0077)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from career_agent.domain.notification import (
    Notification,
    NotificationCategory,
    NotificationType,
)
from career_agent.storage.sqlite import SqliteNotificationStore


class NotificationEngine:
    """Creates a :class:`Notification`, persists it, and returns it.

    Deliberately does not decide delivery -- that is
    :class:`~career_agent.agents.notifications.dispatcher.NotificationDispatcher`'s
    job, kept as a separate step so "a notification exists" and "a
    notification was delivered somewhere" stay two different, separately
    testable facts.
    """

    def __init__(self, store: SqliteNotificationStore) -> None:
        """Configure with the store to persist every created notification into."""
        self._store = store

    def create(
        self,
        *,
        user_id: str,
        type: NotificationType,
        category: NotificationCategory,
        title: str,
        message: str,
        now: datetime | None = None,
    ) -> Notification:
        """Create, persist, and return a new notification for ``user_id``."""
        notification = Notification(
            id=str(uuid.uuid4()),
            type=type,
            category=category,
            title=title,
            message=message,
            created_at=now or datetime.now(UTC),
        )
        self._store.save(notification, user_id=user_id)
        return notification
