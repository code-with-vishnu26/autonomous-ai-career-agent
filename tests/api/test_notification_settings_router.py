"""Phase 58 (ADR-0077): the `/notification-settings` preferences endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter

_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """The rate limiter is process-global (ADR-0074) -- reset it so an
    earlier test's attempts never count against a later test's budget."""
    auth_rate_limiter._hits.clear()
    yield
    auth_rate_limiter._hits.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _register(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    return response.json()["access_token"]


def test_get_requires_authentication(client: TestClient) -> None:
    assert client.get("/notification-settings").status_code == 401


def test_get_before_any_save_returns_defaults(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/notification-settings", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enable_in_app"] is True
    assert body["enable_email"] is False
    assert body["webhook_configured"] is False


def test_patch_updates_preferences_and_round_trips(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    update = client.patch(
        "/notification-settings",
        json={"enable_email": True, "enable_digests": False},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["enable_email"] is True
    assert update.json()["enable_digests"] is False

    fetched = client.get("/notification-settings", headers=headers)
    assert fetched.json()["enable_email"] is True
    assert fetched.json()["enable_digests"] is False


def test_patch_sets_webhook_without_ever_echoing_the_url(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.patch(
        "/notification-settings",
        json={"webhook_url": "https://hooks.example.com/secret-token"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["webhook_configured"] is True
    assert "secret-token" not in response.text


def test_patch_empty_webhook_url_clears_it(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.patch(
        "/notification-settings",
        json={"webhook_url": "https://hooks.example.com/x"},
        headers=headers,
    )
    response = client.patch(
        "/notification-settings", json={"webhook_url": ""}, headers=headers
    )
    assert response.json()["webhook_configured"] is False


def test_settings_are_isolated_per_user(client: TestClient) -> None:
    token_a = _register(client, email="a@example.com")
    token_b = _register(client, email="b@example.com")
    client.patch(
        "/notification-settings",
        json={"enable_email": True},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    response_b = client.get(
        "/notification-settings", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response_b.json()["enable_email"] is False
