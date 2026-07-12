"""Composition-root-style store construction for the API (Phase 54).

Mirrors how ``cli.py`` builds a store per command from ``Settings.database_path``
-- no new resolution logic, no caching/pooling beyond what the store classes
already do (``sqlite3.connect`` per call, same as every CLI command).
"""

from __future__ import annotations

from pathlib import Path

from career_agent.core.config import Settings
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteDeliveryAttemptStore,
    SqliteNotificationPreferencesStore,
    SqliteNotificationStore,
    SqlitePasswordResetTokenStore,
    SqliteRefreshTokenStore,
    SqliteResumeVariantStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
    SqliteUserPreferencesStore,
    SqliteUserStore,
    SqliteWebhookSubscriptionStore,
)


def get_settings() -> Settings:
    """A fresh ``Settings`` read from the environment/``.env`` on each call.

    Deliberately uncached: ``Settings`` construction is cheap (pydantic
    field parsing, no I/O beyond ``.env``), and caching would make the API
    process insensitive to a changed ``DATABASE_PATH`` env var without a
    restart -- worse, it would make per-test env isolation
    (``monkeypatch.setenv``) silently stale across tests in the same
    process. The CLI re-reads ``Settings`` fresh per command for the same
    reason.
    """
    return Settings()


def _database_path() -> Path:
    return Path(get_settings().database_path)


def get_application_session_store() -> SqliteApplicationSessionStore:
    """Store backing ``career-agent prepare``'s output."""
    return SqliteApplicationSessionStore(_database_path())


def get_review_session_store() -> SqliteReviewSessionStore:
    """Store backing ``career-agent review``'s output."""
    return SqliteReviewSessionStore(_database_path())


def get_submission_result_store() -> SqliteSubmissionResultStore:
    """Store backing ``career-agent submit``'s output."""
    return SqliteSubmissionResultStore(_database_path())


def get_resume_variant_store() -> SqliteResumeVariantStore:
    """Store backing the résumé variants ``career-agent prepare`` builds."""
    return SqliteResumeVariantStore(_database_path())


def get_user_store() -> SqliteUserStore:
    """Account store (Phase 56, ADR-0074)."""
    return SqliteUserStore(_database_path())


def get_refresh_token_store() -> SqliteRefreshTokenStore:
    """Refresh-token store (Phase 56, ADR-0074)."""
    return SqliteRefreshTokenStore(_database_path())


def get_password_reset_token_store() -> SqlitePasswordResetTokenStore:
    """Password-reset-token store (Phase 56, ADR-0074)."""
    return SqlitePasswordResetTokenStore(_database_path())


def get_user_preferences_store() -> SqliteUserPreferencesStore:
    """Per-user Job Search Preferences store (Phase 56, ADR-0074)."""
    return SqliteUserPreferencesStore(_database_path())


def get_notification_store() -> SqliteNotificationStore:
    """Notification store (Phase 58, ADR-0077)."""
    return SqliteNotificationStore(_database_path())


def get_notification_preferences_store() -> SqliteNotificationPreferencesStore:
    """Per-user notification preferences store (Phase 58, ADR-0077)."""
    return SqliteNotificationPreferencesStore(_database_path())


def get_delivery_attempt_store() -> SqliteDeliveryAttemptStore:
    """Notification delivery-attempt store (Phase 58, ADR-0077)."""
    return SqliteDeliveryAttemptStore(_database_path())


def get_webhook_subscription_store() -> SqliteWebhookSubscriptionStore:
    """Per-user webhook-URL store (Phase 58, ADR-0077)."""
    return SqliteWebhookSubscriptionStore(_database_path())
