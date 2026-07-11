"""Phase 56 (ADR-0074): the ``/auth/*`` endpoints, end to end via TestClient."""

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
from career_agent.storage.sqlite import SqlitePasswordResetTokenStore, SqliteUserStore

_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """The rate limiter is process-global (Phase 56, ADR-0074) -- without
    resetting it, an earlier test's attempts would count against a later
    test's budget and produce a flaky 429."""
    auth_rate_limiter._hits.clear()
    yield
    auth_rate_limiter._hits.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _db_path() -> Path:
    return Path("career_agent.db")


def test_register_returns_access_token_and_sets_refresh_cookie(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "new@example.com"
    assert "hashed_password" not in body["user"]
    assert "refresh_token" in response.cookies


def test_register_rejects_a_short_password(client: TestClient) -> None:
    response = client.post(
        "/auth/register", json={"email": "new@example.com", "password": "short"}
    )
    assert response.status_code == 400


def test_register_rejects_a_duplicate_email(client: TestClient) -> None:
    client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "another-password"},
    )
    assert response.status_code == 409


def test_login_with_correct_credentials_succeeds(client: TestClient) -> None:
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_with_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "wrong"}
    )
    assert response.status_code == 401


def test_login_with_unknown_email_returns_the_same_401(client: TestClient) -> None:
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )
    assert response.status_code == 401


def test_me_with_a_valid_token_returns_the_account(client: TestClient) -> None:
    register = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    token = register.json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


def test_me_without_a_token_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_refresh_rotates_the_token_and_the_old_cookie_stops_working(
    client: TestClient,
) -> None:
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    old_refresh_cookie = client.cookies["refresh_token"]

    first_refresh = client.post("/auth/refresh")
    assert first_refresh.status_code == 200

    # Replay the now-rotated-away cookie: must fail, not succeed again.
    client.cookies.set("refresh_token", old_refresh_cookie)
    replay = client.post("/auth/refresh")
    assert replay.status_code == 401


def test_refresh_without_a_cookie_returns_401(client: TestClient) -> None:
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_logout_revokes_the_refresh_token(client: TestClient) -> None:
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    logout = client.post("/auth/logout")
    assert logout.status_code == 204
    # The cookie was cleared, so a follow-up refresh has nothing to present.
    refresh = client.post("/auth/refresh")
    assert refresh.status_code == 401


def test_logout_without_a_cookie_is_still_safe(client: TestClient) -> None:
    response = client.post("/auth/logout")
    assert response.status_code == 204


def test_forgot_password_returns_202_for_a_registered_email(client: TestClient) -> None:
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    response = client.post("/auth/forgot-password", json={"email": "user@example.com"})
    assert response.status_code == 202


def test_forgot_password_returns_the_same_202_for_an_unregistered_email(
    client: TestClient,
) -> None:
    """Never reveals whether an email is registered (Phase 56, ADR-0074)."""
    response = client.post(
        "/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 202


def test_reset_password_with_a_real_token_changes_the_password(
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

    reset = client.post(
        "/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password"},
    )
    assert reset.status_code == 204

    login_old = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "original-password"},
    )
    assert login_old.status_code == 401

    login_new = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "brand-new-password"},
    )
    assert login_new.status_code == 200


def test_reset_password_with_an_unknown_token_returns_400(client: TestClient) -> None:
    response = client.post(
        "/auth/reset-password",
        json={"token": "never-issued", "new_password": "brand-new-password"},
    )
    assert response.status_code == 400


def test_reset_password_revokes_existing_sessions(client: TestClient) -> None:
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
    client.post(
        "/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password"},
    )
    # The refresh cookie from the original registration must no longer work.
    refresh = client.post("/auth/refresh")
    assert refresh.status_code == 401


def test_login_is_rate_limited(client: TestClient) -> None:
    for _ in range(5):
        client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
        )
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
    )
    assert response.status_code == 429


def test_missing_jwt_secret_fails_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 500
