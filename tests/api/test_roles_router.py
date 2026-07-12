"""Phase 60 (ADR-0078): the `/api/roles` reference endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.domain.roles import ROLES

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


def _register(client: TestClient) -> str:
    response = client.post(
        "/auth/register",
        json={"email": "u@example.com", "password": "correct-horse-battery"},
    )
    return response.json()["access_token"]


def test_list_roles_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/roles").status_code == 401


def test_list_roles_returns_every_role(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/api/roles", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    returned_roles = {entry["role"] for entry in response.json()}
    assert returned_roles == set(ROLES)


def test_list_permissions_returns_a_flat_sorted_list(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/api/roles/permissions", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    permissions = response.json()
    assert permissions == sorted(permissions)
    assert "manage_users" in permissions
