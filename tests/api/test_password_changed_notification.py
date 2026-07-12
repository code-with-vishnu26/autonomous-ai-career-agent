"""Phase 58 (ADR-0077): password-reset completion creates a real notification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.core.security import (
    generate_password_reset_token_value,
    hash_opaque_token,
)
from career_agent.storage.sqlite import (
    SqliteNotificationStore,
    SqlitePasswordResetTokenStore,
    SqliteUserStore,
)

_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    auth_rate_limiter._hits.clear()
    yield
    auth_rate_limiter._hits.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _db_path() -> Path:
    return Path("career_agent.db")


def test_completed_reset_creates_a_password_changed_notification(
    client: TestClient,
) -> None:
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "original-password"},
    )
    user = SqliteUserStore(_db_path()).by_email("user@example.com")

    raw_token = generate_password_reset_token_value()
    SqlitePasswordResetTokenStore(_db_path()).save(
        token_id="pr-1",
        user_id=user.id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = client.post(
        "/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password"},
    )
    assert response.status_code == 204

    notifications = SqliteNotificationStore(_db_path()).by_user(user.id)
    assert any(n.category == "password_changed" for n in notifications)
    assert any(n.type == "WARNING" for n in notifications)
