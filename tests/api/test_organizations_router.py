"""Phase 60 (ADR-0078): the `/organizations/*` endpoints."""

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


def test_list_organizations_requires_authentication(client: TestClient) -> None:
    assert client.get("/organizations").status_code == 401


def test_registering_creates_a_personal_organization(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    orgs = response.json()
    assert len(orgs) == 1
    assert orgs[0]["role"] == "owner"


def test_create_organization_makes_the_caller_owner(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/organizations", json={"name": "Acme Corp"}, headers=headers
    )
    assert response.status_code == 201
    assert response.json()["role"] == "owner"
    assert response.json()["name"] == "Acme Corp"


def test_get_organization_requires_membership(client: TestClient) -> None:
    token_a = _register(client, email="a@example.com")
    token_b = _register(client, email="b@example.com")
    org_id = _register_and_get_org_id(client, token_a)

    response = client.get(
        f"/organizations/{org_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response.status_code == 404


def test_get_organization_succeeds_for_a_real_member(client: TestClient) -> None:
    token = _register(client)
    org_id = _register_and_get_org_id(client, token)
    response = client.get(
        f"/organizations/{org_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


def test_rename_organization_requires_manage_users_permission(
    client: TestClient,
) -> None:
    owner_token = _register(client, email="owner@example.com")
    org_id = _register_and_get_org_id(client, owner_token)
    member_token = _register(client, email="member@example.com")
    _accept_as_member(client, owner_token, org_id, member_token, role="member")

    response = client.patch(
        f"/organizations/{org_id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code == 403


def test_rename_organization_succeeds_for_owner(client: TestClient) -> None:
    token = _register(client)
    org_id = _register_and_get_org_id(client, token)
    response = client.patch(
        f"/organizations/{org_id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_organization_requires_delete_permission_owner_only(
    client: TestClient,
) -> None:
    owner_token = _register(client, email="owner2@example.com")
    org_id = _register_and_get_org_id(client, owner_token)
    admin_token = _register(client, email="admin2@example.com")
    _accept_as_member(client, owner_token, org_id, admin_token, role="admin")

    response = client.delete(
        f"/organizations/{org_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 403


def test_delete_organization_succeeds_for_owner(client: TestClient) -> None:
    token = _register(client)
    org_id = _register_and_get_org_id(client, token)
    response = client.delete(
        f"/organizations/{org_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204
    assert (
        client.get(
            f"/organizations/{org_id}", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 404
    )


def _register_and_get_org_id(client: TestClient, token: str) -> str:
    response = client.get(
        "/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()[0]["id"]


def _accept_as_member(
    client: TestClient,
    _owner_token: str,
    org_id: str,
    invitee_token: str,
    *,
    role: str,
) -> None:
    """Test-only shortcut: add ``invitee_token``'s user to ``org_id`` directly.

    Bypasses the real invite/accept HTTP flow (covered by its own tests
    in ``test_team_router.py``) -- here we only need a real, valid
    membership already in place to test permission gating on other
    routes.
    """
    import uuid
    from datetime import UTC, datetime

    from career_agent.core.config import Settings
    from career_agent.domain.team import Membership
    from career_agent.storage.team_store import SqliteMembershipStore

    membership_store = SqliteMembershipStore(Path(Settings().database_path))
    invitee_id = _me(client, invitee_token)["id"]
    membership_store.create(
        Membership(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            user_id=invitee_id,
            role=role,
            joined_at=datetime.now(UTC),
        )
    )


def _me(client: TestClient, token: str) -> dict:
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return response.json()
