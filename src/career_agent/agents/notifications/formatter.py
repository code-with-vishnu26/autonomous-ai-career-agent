"""NotificationFormatter: pure text rendering for in-app/browser display.

Phase 58, ADR-0077.
"""

from __future__ import annotations

from career_agent.domain.notification import Notification

_TYPE_ICON = {
    "INFO": "i",
    "SUCCESS": "✓",
    "WARNING": "!",
    "ERROR": "✕",
    "REMINDER": "⏰",
    "SYSTEM": "⚙",
}


def format_notification_line(notification: Notification) -> str:
    """One-line, plain-text summary -- e.g. for a browser notification body."""
    icon = _TYPE_ICON.get(notification.type, "")
    return f"{icon} {notification.title}: {notification.message}".strip()


def format_notification_full(notification: Notification) -> str:
    """Multi-line, in-app-card-shaped rendering."""
    lines = [notification.title, notification.message]
    if notification.read_at is not None:
        lines.append(f"Read {notification.read_at.isoformat()}")
    return "\n".join(lines)
