"""Phase 58 (ADR-0077): pure notification text rendering."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.agents.notifications.formatter import (
    format_notification_full,
    format_notification_line,
)
from career_agent.domain.notification import Notification


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


def test_format_notification_line_includes_title_and_message():
    line = format_notification_line(_notification())
    assert "Prepared" in line
    assert "Ready for review." in line


def test_format_notification_line_uses_the_type_icon():
    assert format_notification_line(_notification(type="ERROR")).startswith("✕")


def test_format_notification_full_omits_read_line_when_unread():
    rendered = format_notification_full(_notification())
    assert "Read " not in rendered


def test_format_notification_full_includes_read_line_once_read():
    rendered = format_notification_full(
        _notification(read_at=datetime.now(UTC))
    )
    assert "Read" in rendered
