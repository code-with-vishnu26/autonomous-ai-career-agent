"""Phase 56 (ADR-0074): user/refresh/reset-token/preferences stores + migration."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from career_agent.core.security import hash_opaque_token, hash_password
from career_agent.domain.job_preferences import JobPreferences
from career_agent.domain.models import TailoredContent
from career_agent.domain.resume_variants import ResumeVariant
from career_agent.domain.user import User
from career_agent.storage.sqlite import (
    SqlitePasswordResetTokenStore,
    SqliteRefreshTokenStore,
    SqliteResumeVariantStore,
    SqliteUserPreferencesStore,
    SqliteUserStore,
    migrate_to_multi_user,
)


def _user(**overrides: object) -> User:
    fields = {
        "id": "user-1",
        "email": "person@example.com",
        "hashed_password": hash_password("irrelevant-not-checked-here"),
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return User(**fields)


class TestSqliteUserStore:
    def test_create_then_by_id_round_trips(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "db.sqlite")
        store.create(_user())
        found = store.by_id("user-1")
        assert found is not None
        assert found.email == "person@example.com"

    def test_by_email_round_trips(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "db.sqlite")
        store.create(_user())
        found = store.by_email("person@example.com")
        assert found is not None
        assert found.id == "user-1"

    def test_by_email_is_case_insensitive(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "db.sqlite")
        store.create(_user())
        assert store.by_email("Person@Example.com") is not None

    def test_by_id_unknown_returns_none(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "db.sqlite")
        assert store.by_id("nope") is None

    def test_duplicate_email_raises_integrity_error(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "db.sqlite")
        store.create(_user(id="user-1"))
        with pytest.raises(sqlite3.IntegrityError):
            store.create(_user(id="user-2"))

    def test_update_profile_changes_display_name_only(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "db.sqlite")
        store.create(_user())
        store.update_profile("user-1", display_name="Ada")
        found = store.by_id("user-1")
        assert found.display_name == "Ada"
        assert found.email == "person@example.com"

    def test_update_password_changes_the_hash(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "db.sqlite")
        store.create(_user())
        store.update_password("user-1", hashed_password="new-hash")
        assert store.by_id("user-1").hashed_password == "new-hash"

    def test_survives_close_and_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "db.sqlite"
        SqliteUserStore(path).create(_user())
        assert SqliteUserStore(path).by_id("user-1") is not None


class TestSqliteRefreshTokenStore:
    def test_save_then_find_active_round_trips(self, tmp_path: Path) -> None:
        store = SqliteRefreshTokenStore(tmp_path / "db.sqlite")
        store.save(
            token_id="rt-1",
            user_id="user-1",
            token_hash=hash_opaque_token("raw-token"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        found = store.find_active(hash_opaque_token("raw-token"))
        assert found is not None
        assert found["user_id"] == "user-1"

    def test_unknown_hash_returns_none(self, tmp_path: Path) -> None:
        store = SqliteRefreshTokenStore(tmp_path / "db.sqlite")
        assert store.find_active(hash_opaque_token("never-saved")) is None

    def test_revoke_makes_it_inactive(self, tmp_path: Path) -> None:
        store = SqliteRefreshTokenStore(tmp_path / "db.sqlite")
        store.save(
            token_id="rt-1",
            user_id="user-1",
            token_hash=hash_opaque_token("raw-token"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        store.revoke("rt-1")
        assert store.find_active(hash_opaque_token("raw-token")) is None

    def test_revoke_all_for_user_revokes_every_token(self, tmp_path: Path) -> None:
        store = SqliteRefreshTokenStore(tmp_path / "db.sqlite")
        store.save(
            token_id="rt-1",
            user_id="user-1",
            token_hash=hash_opaque_token("token-a"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        store.save(
            token_id="rt-2",
            user_id="user-1",
            token_hash=hash_opaque_token("token-b"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        store.revoke_all_for_user("user-1")
        assert store.find_active(hash_opaque_token("token-a")) is None
        assert store.find_active(hash_opaque_token("token-b")) is None


class TestSqlitePasswordResetTokenStore:
    def test_save_then_find_unused_round_trips(self, tmp_path: Path) -> None:
        store = SqlitePasswordResetTokenStore(tmp_path / "db.sqlite")
        store.save(
            token_id="pr-1",
            user_id="user-1",
            token_hash=hash_opaque_token("raw-token"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        found = store.find_unused(hash_opaque_token("raw-token"))
        assert found is not None
        assert found["user_id"] == "user-1"

    def test_mark_used_prevents_reuse(self, tmp_path: Path) -> None:
        store = SqlitePasswordResetTokenStore(tmp_path / "db.sqlite")
        store.save(
            token_id="pr-1",
            user_id="user-1",
            token_hash=hash_opaque_token("raw-token"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        store.mark_used("pr-1")
        assert store.find_unused(hash_opaque_token("raw-token")) is None


class TestSqliteUserPreferencesStore:
    def test_get_before_any_save_returns_none(self, tmp_path: Path) -> None:
        store = SqliteUserPreferencesStore(tmp_path / "db.sqlite")
        assert store.get("user-1") is None

    def test_save_then_get_round_trips(self, tmp_path: Path) -> None:
        store = SqliteUserPreferencesStore(tmp_path / "db.sqlite")
        prefs = JobPreferences(preferred_titles=["Backend Engineer"])
        store.save("user-1", prefs)
        assert store.get("user-1") == prefs

    def test_save_again_upserts_rather_than_duplicates(self, tmp_path: Path) -> None:
        store = SqliteUserPreferencesStore(tmp_path / "db.sqlite")
        store.save("user-1", JobPreferences(preferred_titles=["A"]))
        store.save("user-1", JobPreferences(preferred_titles=["B"]))
        assert store.get("user-1").preferred_titles == ["B"]

    def test_two_users_have_independent_preferences(self, tmp_path: Path) -> None:
        store = SqliteUserPreferencesStore(tmp_path / "db.sqlite")
        store.save("user-1", JobPreferences(preferred_titles=["A"]))
        store.save("user-2", JobPreferences(preferred_titles=["B"]))
        assert store.get("user-1").preferred_titles == ["A"]
        assert store.get("user-2").preferred_titles == ["B"]


EMAIL = "local@test.invalid"


class TestMigrateToMultiUser:
    def _variant(self) -> ResumeVariant:
        return ResumeVariant(
            id="v1",
            category="backend",
            profile_version="v1",
            content=TailoredContent(summary="s", work=[], skills=[], projects=[]),
            created_at="2026-01-01T00:00:00Z",
        )

    def _seed_pre_phase56_table(self, path: Path) -> None:
        """Simulate a database whose ``resume_variants`` table predates
        the ``user_id`` column entirely -- what every real pre-Phase-56
        database looks like."""
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE resume_variants (id TEXT PRIMARY KEY, category TEXT NOT NULL,"
            " payload TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        variant = self._variant()
        connection.execute(
            "INSERT INTO resume_variants (id, category, payload, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                variant.id,
                variant.category,
                variant.model_dump_json(),
                variant.created_at,
            ),
        )
        connection.commit()
        connection.close()

    def test_creates_a_default_operator_account(self, tmp_path: Path) -> None:
        path = tmp_path / "db.sqlite"
        user_id = migrate_to_multi_user(path, default_operator_email=EMAIL)
        found = SqliteUserStore(path).by_email(EMAIL)
        assert found is not None
        assert found.id == user_id

    def test_is_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "db.sqlite"
        first = migrate_to_multi_user(path, default_operator_email=EMAIL)
        second = migrate_to_multi_user(path, default_operator_email=EMAIL)
        assert first == second

    def test_backfills_pre_existing_rows_to_the_default_operator(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "db.sqlite"
        self._seed_pre_phase56_table(path)
        user_id = migrate_to_multi_user(path, default_operator_email=EMAIL)
        variants = SqliteResumeVariantStore(path).by_user(user_id)
        assert [v.id for v in variants] == ["v1"]

    def test_never_touches_rows_already_owned_by_a_real_user(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "db.sqlite"
        user_id = migrate_to_multi_user(path, default_operator_email=EMAIL)
        store = SqliteResumeVariantStore(path)
        store.save(self._variant(), user_id="someone-else")
        # Re-running the migration must not reassign the already-owned row.
        migrate_to_multi_user(path, default_operator_email=EMAIL)
        assert [v.id for v in store.by_user("someone-else")] == ["v1"]
        assert store.by_user(user_id) == []
