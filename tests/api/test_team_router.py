"""Phase 60 (ADR-0078): the `/team/*` endpoints -- members and invitations."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.core.config import Settings
from career_agent.storage.team_store import SqliteInvitationStore

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


def _me(client: TestClient, token: str) -> dict:
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()


def _my_org_id(client: TestClient, token: str) -> str:
    response = client.get(
        "/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()[0]["id"]


def test_invite_requires_invite_users_permission(client: TestClient) -> None:
    owner_token = _register(client, email="owner@example.com")
    org_id = _my_org_id(client, owner_token)
    other_token = _register(client, email="other@example.com")

    response = client.post(
        f"/team/{org_id}/invite",
        json={"email": "invitee@example.com", "role": "member"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404  # not even a member of org_id


def test_full_invite_and_accept_flow(client: TestClient) -> None:
    owner_token = _register(client, email="owner2@example.com")
    org_id = _my_org_id(client, owner_token)
    headers = {"Authorization": f"Bearer {owner_token}"}

    invite = client.post(
        f"/team/{org_id}/invite",
        json={"email": "newperson@example.com", "role": "recruiter"},
        headers=headers,
    )
    assert invite.status_code == 201
    assert invite.json()["status"] == "PENDING"

    invitee_token = _register(client, email="newperson@example.com")
    raw_token = _mint_matching_raw_token(invite.json()["id"])

    accept = client.post(
        "/team/invite/accept",
        json={"token": raw_token},
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert accept.status_code == 200
    assert accept.json()["role"] == "recruiter"

    members = client.get(f"/team/{org_id}", headers=headers).json()
    assert any(m["email"] == "newperson@example.com" for m in members)


def test_accept_with_email_mismatch_returns_400(client: TestClient) -> None:
    owner_token = _register(client, email="owner3@example.com")
    org_id = _my_org_id(client, owner_token)
    headers = {"Authorization": f"Bearer {owner_token}"}

    invite = client.post(
        f"/team/{org_id}/invite",
        json={"email": "expected@example.com", "role": "member"},
        headers=headers,
    )
    raw_token = _mint_matching_raw_token(invite.json()["id"])

    wrong_person_token = _register(client, email="different@example.com")
    response = client.post(
        "/team/invite/accept",
        json={"token": raw_token},
        headers={"Authorization": f"Bearer {wrong_person_token}"},
    )
    assert response.status_code == 400


def test_accept_unknown_token_returns_400(client: TestClient) -> None:
    token = _register(client)
    response = client.post(
        "/team/invite/accept",
        json={"token": "totally-made-up"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_revoke_invitation(client: TestClient) -> None:
    owner_token = _register(client, email="owner4@example.com")
    org_id = _my_org_id(client, owner_token)
    headers = {"Authorization": f"Bearer {owner_token}"}
    invite = client.post(
        f"/team/{org_id}/invite",
        json={"email": "a@example.com", "role": "member"},
        headers=headers,
    )
    invitation_id = invite.json()["id"]

    response = client.delete(
        f"/team/{org_id}/invitations/{invitation_id}", headers=headers
    )
    assert response.status_code == 204

    invitations = client.get(f"/team/{org_id}/invitations", headers=headers).json()
    revoked = next(i for i in invitations if i["id"] == invitation_id)
    assert revoked["status"] == "REVOKED"


def test_seat_limit_blocks_invites_past_the_free_plans_limit(
    client: TestClient,
) -> None:
    owner_token = _register(client, email="owner5@example.com")
    org_id = _my_org_id(client, owner_token)
    headers = {"Authorization": f"Bearer {owner_token}"}
    # Free plan's max_seats is 3; fill the remaining two seats by
    # actually accepting invitations (the limit counts real members, not
    # pending invitations).
    for email in ("b1@example.com", "b2@example.com"):
        invite = client.post(
            f"/team/{org_id}/invite",
            json={"email": email, "role": "member"},
            headers=headers,
        )
        invitee_token = _register(client, email=email)
        raw_token = _mint_matching_raw_token(invite.json()["id"])
        accept = client.post(
            "/team/invite/accept",
            json={"token": raw_token},
            headers={"Authorization": f"Bearer {invitee_token}"},
        )
        assert accept.status_code == 200

    invite3 = client.post(
        f"/team/{org_id}/invite",
        json={"email": "b3@example.com", "role": "member"},
        headers=headers,
    )
    assert invite3.status_code == 402


def test_update_member_role_requires_manage_users(client: TestClient) -> None:
    owner_token = _register(client, email="owner6@example.com")
    org_id = _my_org_id(client, owner_token)
    owner_id = _me(client, owner_token)["id"]
    headers = {"Authorization": f"Bearer {owner_token}"}

    response = client.patch(
        f"/team/{org_id}/members/{owner_id}", json={"role": "admin"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_remove_member_requires_suspend_users_permission(client: TestClient) -> None:
    owner_token = _register(client, email="owner7@example.com")
    org_id = _my_org_id(client, owner_token)
    headers = {"Authorization": f"Bearer {owner_token}"}
    invite = client.post(
        f"/team/{org_id}/invite",
        json={"email": "removable@example.com", "role": "member"},
        headers=headers,
    )
    invitee_token = _register(client, email="removable@example.com")
    raw_token = _mint_matching_raw_token(invite.json()["id"])
    client.post(
        "/team/invite/accept",
        json={"token": raw_token},
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    invitee_id = _me(client, invitee_token)["id"]

    response = client.delete(f"/team/{org_id}/members/{invitee_id}", headers=headers)
    assert response.status_code == 204
    members = client.get(f"/team/{org_id}", headers=headers).json()
    assert not any(m["user_id"] == invitee_id for m in members)


def _mint_matching_raw_token(invitation_id: str) -> str:
    """Test-only: create a second, storage-level invitation with a known raw token.

    The real API never returns the raw token at all (only the invitee's
    real email delivery carries it) -- there is deliberately no way to
    recover it from the API-created invitation's response. To exercise
    the real accept endpoint, this mirrors the *same* invitation
    (organization/email/role) via ``invitations.create_invitation``
    directly against the same store, with a token this test does know.
    """
    from datetime import UTC, datetime

    from career_agent.invitations import create_invitation

    store = SqliteInvitationStore(Path(Settings().database_path))
    original = store.get(invitation_id)
    _new_invitation, raw_token = create_invitation(
        organization_id=original.organization_id,
        invited_by_user_id=original.invited_by_user_id,
        email=original.email,
        role=original.role,
        invitation_store=store,
        now=datetime.now(UTC),
    )
    return raw_token
