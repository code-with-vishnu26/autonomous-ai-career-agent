"""Phase 67 (ADR-0085): POST /prepare + GET /prepare/{token}.

Web-triggered tailoring that reads the caller's stored Master Profile
(Phase 64) and feeds a READY_FOR_REVIEW ApplicationSession into the
Review Queue. The real LLM tailoring (`prepare_application_for_review`) is
monkeypatched in the happy-path test -- these assert the router's
orchestration (load profile, load opportunity, save session, status
transitions, per-user isolation), not the pipeline itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.models import (
    BasicsSection,
    MasterProfile,
    Opportunity,
    Provenance,
)
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteMasterProfileStore,
    SqliteOpportunityRepository,
)

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


def _db_path() -> Path:
    return Path("career_agent.db")


def _register(client: TestClient, email: str = "user@example.com") -> str:
    return client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]


def _me_id(client: TestClient, token: str) -> str:
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
        "id"
    ]


def _seed_profile(user_id: str) -> None:
    SqliteMasterProfileStore(_db_path()).save(
        user_id,
        MasterProfile(
            version="pending",
            basics=BasicsSection(name="Ada", email="ada@example.com", summary="Eng."),
        ),
    )


def _opportunity(opportunity_id: str = "opp-1") -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="Acme Corp",
        title="Backend Engineer",
        source="ats_api",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://boards.greenhouse.io/acme/jobs/1",
            extraction_confidence=1.0,
        ),
        description_raw="Python and FastAPI backend role.",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _fake_session() -> ApplicationSession:
    return ApplicationSession(
        id="prepared-1",
        provider="greenhouse",
        company="Acme Corp",
        job_title="Backend Engineer",
        url="https://boards.greenhouse.io/acme/jobs/1",
        opportunity_id="opp-1",
        status="READY_FOR_REVIEW",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_start_preparation_requires_authentication(client: TestClient) -> None:
    assert client.post("/prepare", json={"opportunity_id": "opp-1"}).status_code == 401


def test_get_status_unknown_token_is_404(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/prepare/nope", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_prepare_fails_when_no_master_profile(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/prepare", json={"opportunity_id": "opp-1"}, headers=headers
    )
    prep_token = response.json()["token"]
    final = client.get(f"/prepare/{prep_token}", headers=headers).json()
    assert final["status"] == "FAILED"
    assert "onboarding" in final["error"].lower()


async def test_prepare_fails_when_opportunity_not_found(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed_profile(_me_id(client, token))
    response = client.post(
        "/prepare", json={"opportunity_id": "missing"}, headers=headers
    )
    prep_token = response.json()["token"]
    final = client.get(f"/prepare/{prep_token}", headers=headers).json()
    assert final["status"] == "FAILED"
    assert "not found" in final["error"].lower()


async def test_prepare_happy_path_saves_a_reviewable_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_prepare(**_kwargs: object) -> ApplicationSession:
        return _fake_session()

    async def _no_notify(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "career_agent.api.routers.prepare_actions.prepare_application_for_review",
        _fake_prepare,
    )
    monkeypatch.setattr(
        "career_agent.api.routers.prepare_actions._notify", _no_notify
    )

    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    user_id = _me_id(client, token)
    _seed_profile(user_id)
    await SqliteOpportunityRepository(_db_path()).add(_opportunity())

    response = client.post(
        "/prepare", json={"opportunity_id": "opp-1"}, headers=headers
    )
    assert response.status_code == 202
    prep_token = response.json()["token"]

    final = client.get(f"/prepare/{prep_token}", headers=headers).json()
    assert final["status"] == "DONE"
    assert final["application_session_id"] == "prepared-1"

    saved = SqliteApplicationSessionStore(_db_path()).by_user(user_id)
    assert [s.id for s in saved] == ["prepared-1"]


async def test_prepare_token_never_leaks_across_users(client: TestClient) -> None:
    owner_token = _register(client, email="owner@example.com")
    other_token = _register(client, email="other@example.com")
    response = client.post(
        "/prepare",
        json={"opportunity_id": "opp-1"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    prep_token = response.json()["token"]
    leaked = client.get(
        f"/prepare/{prep_token}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert leaked.status_code == 404
