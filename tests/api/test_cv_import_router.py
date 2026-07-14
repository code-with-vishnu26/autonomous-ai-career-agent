"""Phase 71 (ADR-0089): POST /user/master-profile/import (+ /confirm).

Web résumé upload -> review -> promote into the caller's Master Profile.
Exercises the real ``storage/cv_ingest.py`` fail-closed boundary end to
end via HTTP, not mocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter

_JWT_SECRET = "unit-test-secret-not-for-real-use"
_RESUME_TEXT = (
    b"Ada Lovelace\n"
    b"ada@example.com\n"
    b"Skills: Python, SQL, FastAPI\n"
)


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
    return client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]


def _upload(client: TestClient, headers: dict, body: bytes = _RESUME_TEXT):
    return client.post(
        "/user/master-profile/import",
        headers=headers,
        files={"file": ("resume.txt", body, "text/plain")},
    )


def test_upload_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/user/master-profile/import",
        files={"file": ("resume.txt", _RESUME_TEXT, "text/plain")},
    )
    assert response.status_code == 401


def test_upload_extracts_unverified_proposals(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = _upload(client, headers)
    assert response.status_code == 202
    body = response.json()
    assert body["source_type"] == "text"
    field_paths = {p["field_path"] for p in body["proposals"]}
    assert "basics.email" in field_paths
    assert "basics.name" in field_paths
    assert "skills" in field_paths
    # Never touches the profile by itself.
    assert client.get("/user/master-profile", headers=headers).json() is None


def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/user/master-profile/import",
        headers=headers,
        files={"file": ("resume.rtf", b"{\\rtf1 fake}", "application/rtf")},
    )
    assert response.status_code == 400


def test_confirm_unknown_token_is_404(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/user/master-profile/import/nope/confirm",
        json={"decisions": []},
        headers=headers,
    )
    assert response.status_code == 404


def test_confirming_nothing_saves_nothing(client: TestClient) -> None:
    """A proposal never listed in decisions stays UNVERIFIED -- not promoted."""
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    upload = _upload(client, headers).json()

    response = client.post(
        f"/user/master-profile/import/{upload['token']}/confirm",
        json={"decisions": []},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile_saved"] is False
    assert set(body["missing_required_fields"]) == {"name", "email"}
    assert client.get("/user/master-profile", headers=headers).json() is None


def test_confirming_name_and_email_saves_a_real_profile(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    upload = _upload(client, headers).json()

    name_id = next(
        p["proposal_id"]
        for p in upload["proposals"]
        if p["field_path"] == "basics.name"
    )
    email_id = next(
        p["proposal_id"]
        for p in upload["proposals"]
        if p["field_path"] == "basics.email"
    )
    response = client.post(
        f"/user/master-profile/import/{upload['token']}/confirm",
        json={
            "decisions": [
                {"proposal_id": name_id, "confirmed": True},
                {"proposal_id": email_id, "confirmed": True},
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile_saved"] is True
    assert body["profile"]["basics"]["name"] == "Ada Lovelace"
    assert body["profile"]["basics"]["email"] == "ada@example.com"
    outcomes = {r["proposal_id"]: r["outcome"] for r in body["results"]}
    assert outcomes[name_id] == "ADD"
    assert outcomes[email_id] == "ADD"

    saved = client.get("/user/master-profile", headers=headers).json()
    assert saved["basics"]["name"] == "Ada Lovelace"


def test_rejected_proposal_is_never_promoted(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    upload = _upload(client, headers).json()
    name_id = next(
        p["proposal_id"]
        for p in upload["proposals"]
        if p["field_path"] == "basics.name"
    )
    email_id = next(
        p["proposal_id"]
        for p in upload["proposals"]
        if p["field_path"] == "basics.email"
    )
    response = client.post(
        f"/user/master-profile/import/{upload['token']}/confirm",
        json={
            "decisions": [
                {"proposal_id": name_id, "confirmed": True},
                {"proposal_id": email_id, "confirmed": False},
            ]
        },
        headers=headers,
    )
    body = response.json()
    outcomes = {r["proposal_id"]: r["outcome"] for r in body["results"]}
    assert outcomes[email_id] == "REJECT"
    assert body["profile_saved"] is False  # still missing a confirmed email


def test_does_not_overwrite_an_existing_different_trusted_value(
    client: TestClient,
) -> None:
    """A confirmed proposal never silently overwrites a different existing fact."""
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        "/user/master-profile",
        json={"basics": {"name": "Existing Name", "email": "existing@example.com"}},
        headers=headers,
    )
    upload = _upload(client, headers).json()
    name_id = next(
        p["proposal_id"]
        for p in upload["proposals"]
        if p["field_path"] == "basics.name"
    )
    response = client.post(
        f"/user/master-profile/import/{upload['token']}/confirm",
        json={"decisions": [{"proposal_id": name_id, "confirmed": True}]},
        headers=headers,
    )
    body = response.json()
    outcomes = {r["proposal_id"]: r["outcome"] for r in body["results"]}
    assert outcomes[name_id] == "REQUIRES_RESOLUTION"
    saved = client.get("/user/master-profile", headers=headers).json()
    assert saved["basics"]["name"] == "Existing Name"  # unchanged


def test_import_token_never_leaks_across_users(client: TestClient) -> None:
    owner_token = _register(client, email="owner@example.com")
    other_token = _register(client, email="other@example.com")
    upload = _upload(client, {"Authorization": f"Bearer {owner_token}"}).json()

    response = client.post(
        f"/user/master-profile/import/{upload['token']}/confirm",
        json={"decisions": []},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404
