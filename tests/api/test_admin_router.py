"""Phase 60 (ADR-0078): the `/api/admin/*` platform-superadmin endpoints."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.storage.sqlite import SqliteUserStore

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


def _promote_to_admin(email: str) -> None:
    """Test-only: reproduce "the operator already made me admin".

    No API surface promotes a user to platform admin (deliberately --
    that is an operator/ops action, not self-service), so this reaches
    into the database directly rather than exercising a route that
    doesn't exist.
    """
    import sqlite3

    db_path = Path(os.environ["DATABASE_PATH"])
    store = SqliteUserStore(db_path)
    user = store.by_email(email)
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user.id,))


def test_list_all_organizations_requires_admin_role(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/api/admin/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_list_all_organizations_succeeds_for_a_platform_admin(
    client: TestClient,
) -> None:
    _register(client, email="regular@example.com")
    admin_token = _register(client, email="admin@example.com")
    _promote_to_admin("admin@example.com")

    response = client.get(
        "/api/admin/organizations", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_organization_members_requires_admin_role(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/api/admin/organizations/some-org-id/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
