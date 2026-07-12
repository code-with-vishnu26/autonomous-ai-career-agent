"""Phase 57 (ADR-0075): the `/coach/*` Career Coach endpoints.

Deterministic endpoints (resume-analysis, job-match, skill-gap) exercise
the real deterministic pipeline end to end. LLM-backed endpoints
(resume-suggestions, cover-letter/transform, interview-prep) monkeypatch
``select_coach_advisor``/``_require_settings_ready`` so no real network
call or promptfoo artifact is needed -- the promptfoo-gate wiring itself
is proven by ``cli.py``'s existing tests; this only proves the router
calls it and turns its failure into a clean HTTP error.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.core.security import create_access_token, hash_password
from career_agent.domain.user import User
from career_agent.llm.providers import NoLLMProviderConfiguredError
from career_agent.storage.sqlite import SqliteUserStore
from tests._fakes import FakeCareerCoachAdvisor, FakeClaimVerifier

TEST_USER_ID = "u1"
_TEST_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _TEST_JWT_SECRET)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    test_client = TestClient(app)
    SqliteUserStore(Path("career_agent.db")).create(
        User(
            id=TEST_USER_ID,
            email="test-user@example.com",
            hashed_password=hash_password("irrelevant-not-checked-here"),
            role="user",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    token = create_access_token(
        user_id=TEST_USER_ID,
        role="user",
        secret_key=_TEST_JWT_SECRET,
        expires_in_minutes=15,
    )
    test_client.headers.update({"Authorization": f"Bearer {token}"})
    return test_client


def test_resume_analysis_requires_auth() -> None:
    anonymous = TestClient(create_app())
    response = anonymous.post(
        "/coach/resume-analysis", json={"resume_text": "x", "jd_text": "y"}
    )
    assert response.status_code == 401


def test_resume_analysis_returns_deterministic_result(client: TestClient) -> None:
    response = client.post(
        "/coach/resume-analysis",
        json={"resume_text": "I know Python.", "jd_text": "Python developer needed."},
    )
    assert response.status_code == 200
    assert response.json()["ats_score"] == 100.0


def test_job_match_returns_deterministic_result(client: TestClient) -> None:
    response = client.post(
        "/coach/job-match",
        json={"resume_text": "I know Python.", "jd_text": "Python developer needed."},
    )
    assert response.status_code == 200
    assert response.json()["match_score"] == 100.0


def test_skill_gap_returns_deterministic_result(client: TestClient) -> None:
    response = client.post(
        "/coach/skill-gap",
        json={"resume_text": "no relevant skills", "jd_text": "Needs Kubernetes."},
    )
    assert response.status_code == 200
    assert response.json()["missing_skills"][0]["keyword"] == "Kubernetes"


def test_resume_suggestions_returns_verified_suggestions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from career_agent.api.routers import coach as coach_router
    from career_agent.core.interfaces import ClaimVerdict

    advisor = FakeCareerCoachAdvisor(
        '[{"original": "Wrote code.", "suggested": "Built the API.", "reason": "x"}]'
    )
    verifier = FakeClaimVerifier(
        {"Built the API.": ClaimVerdict(verified=True, confidence=0.9)}
    )
    monkeypatch.setattr(coach_router, "select_coach_advisor", lambda settings: advisor)
    monkeypatch.setattr(
        coach_router, "_require_settings_ready", lambda settings: verifier
    )
    response = client.post(
        "/coach/resume-suggestions",
        json={"resume_text": "Wrote code.", "jd_text": "Looking for an API builder."},
    )
    assert response.status_code == 200
    assert response.json()[0]["suggested"] == "Built the API."


def test_resume_suggestions_502_on_advisor_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from career_agent.api.routers import coach as coach_router

    advisor = FakeCareerCoachAdvisor(RuntimeError("down"))
    monkeypatch.setattr(coach_router, "select_coach_advisor", lambda settings: advisor)
    monkeypatch.setattr(
        coach_router, "_require_settings_ready", lambda settings: FakeClaimVerifier({})
    )
    response = client.post(
        "/coach/resume-suggestions", json={"resume_text": "x", "jd_text": "y"}
    )
    assert response.status_code == 502


def test_resume_suggestions_503_when_no_provider_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from career_agent.api.routers import coach as coach_router

    def _raise(settings: object) -> None:
        raise NoLLMProviderConfiguredError("no key set")

    monkeypatch.setattr(coach_router, "select_claim_verifier", _raise)
    response = client.post(
        "/coach/resume-suggestions", json={"resume_text": "x", "jd_text": "y"}
    )
    assert response.status_code == 503


def test_interview_prep_returns_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from career_agent.api.routers import coach as coach_router

    advisor = FakeCareerCoachAdvisor(
        '{"technical_questions": [], "behavioral_questions": [], '
        '"role_specific_questions": [], "star_guidance": "Use STAR."}'
    )
    monkeypatch.setattr(coach_router, "select_coach_advisor", lambda settings: advisor)
    response = client.post("/coach/interview-prep", json={"jd_text": "Python role."})
    assert response.status_code == 200
    assert response.json()["star_guidance"] == "Use STAR."
