"""Phase 58 (ADR-0077): per-user NotificationPreferences."""

from __future__ import annotations

from career_agent.domain.notification_preferences import NotificationPreferences


def test_defaults_are_in_app_only():
    preferences = NotificationPreferences()
    assert preferences.enable_in_app is True
    assert preferences.enable_email is False
    assert preferences.enable_browser is True


def test_wants_category_true_for_everything_when_list_is_empty():
    preferences = NotificationPreferences()
    assert preferences.wants_category("resume_prepared") is True
    assert preferences.wants_category("submission_failed") is True


def test_wants_category_only_true_for_selected_categories_once_customized():
    preferences = NotificationPreferences(categories=["review_approved"])
    assert preferences.wants_category("review_approved") is True
    assert preferences.wants_category("resume_prepared") is False
