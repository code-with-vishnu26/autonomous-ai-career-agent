"""Phase 58 (ADR-0077): Notification / DeliveryAttempt domain models."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.notification import DeliveryAttempt, Notification


def test_notification_carries_no_user_id_field():
    notification = Notification(
        id="n1",
        type="SUCCESS",
        category="resume_prepared",
        title="Prepared",
        message="Ready for review.",
        created_at=datetime.now(UTC),
    )
    assert "user_id" not in notification.model_dump()


def test_notification_defaults_to_unread():
    notification = Notification(
        id="n1",
        type="INFO",
        category="system",
        title="t",
        message="m",
        created_at=datetime.now(UTC),
    )
    assert notification.read_at is None


def test_delivery_attempt_records_status_and_detail():
    attempt = DeliveryAttempt(
        id="d1",
        notification_id="n1",
        channel="email",
        status="FAILED",
        detail="SMTP connection refused",
        attempted_at=datetime.now(UTC),
    )
    assert attempt.status == "FAILED"
    assert "refused" in attempt.detail


def test_delivery_attempt_detail_defaults_to_empty_string():
    attempt = DeliveryAttempt(
        id="d1",
        notification_id="n1",
        channel="in_app",
        status="SENT",
        attempted_at=datetime.now(UTC),
    )
    assert attempt.detail == ""
