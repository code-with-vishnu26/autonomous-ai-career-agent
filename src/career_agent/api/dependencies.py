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
    SqliteResumeVariantStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
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
