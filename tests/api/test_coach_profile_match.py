"""Phase 66 (ADR-0084): POST /coach/profile-match.

Scores the caller's stored Master Profile against a JD using the same
deterministic ADR-0075 keyword scorers, so onboarded users never re-type
their résumé. Deterministic -- these tests need no LLM/provider config.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.core.security import create_access_token, hash_password
from career_agent.domain.models import BasicsSection, MasterProfile, WorkEntry
from career_agent.domain.user import User
from career_agent.storage.sqlite import SqliteMasterProfileStore, SqliteUserStore

_JWT_SECRET = "unit-test-secret-not-for-real-use"
_OWNER_ID = "owner-user-id"
_OTHER_ID = "other-user-id"


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


def _db_path() -> Path:
    return Path("career_agent.db")


def _token(user_id: str, email: str) -> str:
    SqliteUserStore(_db_path()).create(
        User(
            id=user_id,
            email=email,
            hashed_password=hash_password("irrelevant-not-checked-here"),
            role="user",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    return create_access_token(
        user_id=user_id, role="user", secret_key=_JWT_SECRET, expires_in_minutes=15
    )


def _seed_profile(user_id: str) -> None:
    SqliteMasterProfileStore(_db_path()).save(
        user_id,
        MasterProfile(
            version="pending",
            basics=BasicsSection(
                name="Ada",
                email="ada@example.com",
                summary="Backend engineer skilled in Python and FastAPI.",
            ),
            work=[
                WorkEntry(
                    id="w1",
                    name="Acme",
                    position="Backend Engineer",
                    start_date="2020-01-01",
                    highlights=["Built REST APIs in Python", "Ran Postgres"],
                )
            ],
        ),
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_requires_authentication(client: TestClient) -> None:
    response = client.post("/coach/profile-match", json={"jd_text": "Python role"})
    assert response.status_code == 401


def test_404_when_no_profile_onboarded_yet(client: TestClient) -> None:
    token = _token(_OWNER_ID, "owner@example.com")
    response = client.post(
        "/coach/profile-match",
        json={"jd_text": "Python backend engineer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_scores_stored_profile_against_jd(client: TestClient) -> None:
    token = _token(_OWNER_ID, "owner@example.com")
    _seed_profile(_OWNER_ID)
    response = client.post(
        "/coach/profile-match",
        json={"jd_text": "Looking for a Python backend engineer with FastAPI."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile_version"].startswith("sha256:")
    assert body["match"]["match_score"] > 0
    assert "matched_keywords" in body["match"]
    assert "qualifies_percent" in body["skill_gap"]
    assert "missing_skills" in body["skill_gap"]


def test_one_users_profile_never_scores_for_another(client: TestClient) -> None:
    _seed_profile(_OWNER_ID)
    other_token = _token(_OTHER_ID, "other@example.com")
    response = client.post(
        "/coach/profile-match",
        json={"jd_text": "Python backend engineer"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404  # the other user has no profile of their own
