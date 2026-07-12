"""Phase 60 (ADR-0078): the `/api/audit/{organization_id}` endpoint."""

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


def _my_org_id(client: TestClient, token: str) -> str:
    response = client.get(
        "/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()[0]["id"]


def test_audit_log_requires_manage_users_permission(client: TestClient) -> None:
    owner_token = _register(client, email="owner@example.com")
    org_id = _my_org_id(client, owner_token)
    other_token = _register(client, email="other@example.com")

    response = client.get(
        f"/api/audit/{org_id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert response.status_code == 404


def test_audit_log_records_organization_creation(client: TestClient) -> None:
    token = _register(client)
    org_id = _my_org_id(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/audit/{org_id}", headers=headers)
    assert response.status_code == 200


def test_audit_log_records_a_real_invite(client: TestClient) -> None:
    token = _register(client)
    org_id = _my_org_id(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        f"/team/{org_id}/invite",
        json={"email": "a@example.com", "role": "member"},
        headers=headers,
    )

    entries = client.get(f"/api/audit/{org_id}", headers=headers).json()
    assert any("invitation_sent" in entry["action"] for entry in entries)
