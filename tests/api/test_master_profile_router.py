"""Phase 64 (ADR-0082): `/user/master-profile` GET/PUT."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.storage.profile import ProfileValidationError

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


def _register(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    return response.json()["access_token"]


def _valid_body() -> dict:
    return {
        "basics": {"name": "Ada Lovelace", "email": "ada@example.com"},
        "work": [
            {
                "id": "work-1",
                "name": "Acme",
                "position": "Engineer",
                "start_date": "2020-01-01",
                "highlights": ["Shipped things."],
            }
        ],
        "education": [],
        "skills": [],
        "projects": [],
    }


def test_get_requires_authentication(client: TestClient) -> None:
    response = client.get("/user/master-profile")
    assert response.status_code == 401


def test_get_returns_none_before_onboarding(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/user/master-profile", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() is None


def test_put_then_get_round_trips(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    put_response = client.put(
        "/user/master-profile", json=_valid_body(), headers=headers
    )
    assert put_response.status_code == 200
    body = put_response.json()
    assert body["basics"]["name"] == "Ada Lovelace"
    assert body["version"].startswith("sha256:")

    get_response = client.get("/user/master-profile", headers=headers)
    assert get_response.json() == body


def test_put_ignores_client_supplied_version(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = _valid_body()
    payload["version"] = "fabricated"  # not a field on MasterProfileUpdate -- ignored
    response = client.put("/user/master-profile", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["version"] != "fabricated"


def test_put_rejects_duplicate_ids_across_sections(client: TestClient) -> None:
    """TestClient re-raises an unhandled exception by default (rather than
    returning the 500 a real deployment would) -- proving the *same*
    cross-section id-uniqueness check the file loader enforces is real
    without needing ``raise_server_exceptions=False`` plumbing just for
    this one test."""
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = _valid_body()
    payload["projects"] = [{"id": "work-1", "name": "Side Project"}]  # dup of work id
    with pytest.raises(ProfileValidationError):
        client.put("/user/master-profile", json=payload, headers=headers)


def test_profile_never_leaks_across_users(client: TestClient) -> None:
    owner_token = _register(client, email="owner@example.com")
    other_token = _register(client, email="other@example.com")
    client.put(
        "/user/master-profile",
        json=_valid_body(),
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    response = client.get(
        "/user/master-profile", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert response.json() is None
