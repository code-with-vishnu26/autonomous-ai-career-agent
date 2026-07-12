"""Phase 58 (ADR-0077): reusable email templates -- pure (subject, body) functions."""

from __future__ import annotations

from career_agent.agents.notifications.templates import (
    digest_email,
    password_changed_email,
    password_reset_email,
    review_reminder_email,
    submission_confirmation_email,
    welcome_email,
)


def test_welcome_email_uses_display_name_when_present():
    subject, body = welcome_email(display_name="Ada", email="ada@example.com")
    assert "Welcome" in subject
    assert "Ada" in body


def test_welcome_email_falls_back_to_email_when_no_display_name():
    _subject, body = welcome_email(display_name=None, email="ada@example.com")
    assert "ada@example.com" in body


def test_password_reset_email_includes_the_link():
    _subject, body = password_reset_email(reset_link="https://app/reset?token=abc")
    assert "https://app/reset?token=abc" in body


def test_password_changed_email_warns_about_unrecognized_changes():
    _subject, body = password_changed_email()
    assert "didn't make this change" in body


def test_review_reminder_email_includes_the_count():
    subject, body = review_reminder_email(count=3)
    assert "3" in subject
    assert "3" in body


def test_submission_confirmation_email_includes_company_title_status():
    subject, body = submission_confirmation_email(
        company="Acme", job_title="Backend Engineer", status="SUBMITTED"
    )
    assert "Acme" in subject
    assert "Backend Engineer" in body
    assert "SUBMITTED" in body


def test_digest_email_joins_summary_lines():
    _subject, body = digest_email(
        period="daily", summary_lines=["2 prepared", "1 submitted"]
    )
    assert "2 prepared" in body
    assert "1 submitted" in body


def test_digest_email_handles_no_activity():
    _subject, body = digest_email(period="daily", summary_lines=[])
    assert "Nothing new" in body
