"""Phase 56 (ADR-0074): the ``/user/*`` account-profile/preferences endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app

_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _register(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    return response.json()["access_token"]


def test_update_profile_changes_display_name(client: TestClient) -> None:
    token = _register(client)
    response = client.put(
        "/user/profile",
        json={"display_name": "Ada Lovelace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Ada Lovelace"


def test_update_profile_requires_authentication(client: TestClient) -> None:
    response = client.put("/user/profile", json={"display_name": "Ada"})
    assert response.status_code == 401


def test_get_preferences_before_any_save_returns_defaults(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/user/preferences", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["preferred_titles"] == []


def test_update_then_get_preferences_round_trips(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    update = client.put(
        "/user/preferences",
        json={"preferred_titles": ["Backend Engineer"]},
        headers=headers,
    )
    assert update.status_code == 200
    fetched = client.get("/user/preferences", headers=headers)
    assert fetched.json()["preferred_titles"] == ["Backend Engineer"]


def test_preferences_are_isolated_per_user(client: TestClient) -> None:
    token_a = _register(client, email="a@example.com")
    token_b = _register(client, email="b@example.com")
    client.put(
        "/user/preferences",
        json={"preferred_titles": ["A's role"]},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    response_b = client.get(
        "/user/preferences", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response_b.json()["preferred_titles"] == []
