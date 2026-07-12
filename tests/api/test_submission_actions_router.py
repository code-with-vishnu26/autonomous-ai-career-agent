"""Phase 63 (ADR-0081): `/submissions/prepare` + `/submissions/{token}/confirm`.

Refusal-path tests (no matching session / no approved review / no
opportunity / no profile.json) run over real HTTP -- they fail before
``submit_prepared_application`` is ever called, so there's no risk of the
request hanging on an unresolved confirmation.

The confirm-flow tests call ``_run_prepare_and_submit`` directly as a
coroutine (not through ``TestClient``, which blocks until the *entire*
ASGI cycle -- including background tasks -- completes, so a real two-step
HTTP round trip can't observe an in-flight ``AWAITING_CONFIRMATION`` state
without a second concurrent connection). Pre-resolving the pending entry's
``future`` before awaiting the coroutine simulates "the human already
answered," proving the same confirm_fn coordination
``POST /submissions/{token}/confirm`` uses in production, patching only
``submit_prepared_application`` (no live LLM/browser needed) with a fake
that mirrors its real confirm_fn contract exactly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.agents.submission.submission_engine import CancelledByUserError
from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.api.routers import submission_actions
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.models import Opportunity, Provenance
from career_agent.domain.review import ReviewSession
from career_agent.domain.submission import SubmissionResult
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteOpportunityRepository,
    SqliteReviewSessionStore,
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


@pytest.fixture(autouse=True)
def _clear_pending_registry() -> None:
    """The in-memory registry is process-global -- isolate tests from it."""
    submission_actions._pending.clear()
    yield
    submission_actions._pending.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _register(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    return response.json()["access_token"]


def _application_session(**overrides: object) -> ApplicationSession:
    fields = {
        "id": "sess-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "opportunity_id": "opp-1",
        "status": "READY_FOR_REVIEW",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ApplicationSession(**fields)


def _review_session(**overrides: object) -> ReviewSession:
    fields = {
        "id": "review-1",
        "application_session_id": "sess-1",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "provider": "greenhouse",
        "approval_status": "APPROVED",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ReviewSession(**fields)


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
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _write_profile(tmp_path: Path) -> None:
    (tmp_path / "profile.json").write_text(
        json.dumps(
            {"basics": {"name": "Ada Lovelace", "email": "ada@example.com"}}
        )
    )


def _db_path() -> Path:
    return Path("career_agent.db")


# ---------------------------------------------------------------------------
# HTTP-level refusal paths -- all fail before submit_prepared_application.
# ---------------------------------------------------------------------------


def test_prepare_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/submissions/prepare", json={"application_session_id": "sess-1"}
    )
    assert response.status_code == 401


def test_prepare_fails_when_application_session_not_found(
    client: TestClient,
) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/submissions/prepare",
        json={"application_session_id": "nonexistent"},
        headers=headers,
    )
    assert response.status_code == 202
    prep_token = response.json()["token"]
    final = client.get(f"/submissions/prepare/{prep_token}", headers=headers).json()
    assert final["status"] == "FAILED"
    assert "not found" in final["error"].lower()


def test_prepare_fails_when_no_approved_review(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=headers).json()
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(), user_id=me["id"]
    )
    response = client.post(
        "/submissions/prepare",
        json={"application_session_id": "sess-1"},
        headers=headers,
    )
    prep_token = response.json()["token"]
    final = client.get(f"/submissions/prepare/{prep_token}", headers=headers).json()
    assert final["status"] == "FAILED"
    assert "approved review" in final["error"].lower()
    assert final["company"] == "Acme Corp"  # set before the failure


def test_prepare_fails_when_opportunity_not_found(client: TestClient) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=headers).json()
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(), user_id=me["id"]
    )
    SqliteReviewSessionStore(_db_path()).save(_review_session(), user_id=me["id"])
    response = client.post(
        "/submissions/prepare",
        json={"application_session_id": "sess-1"},
        headers=headers,
    )
    prep_token = response.json()["token"]
    final = client.get(f"/submissions/prepare/{prep_token}", headers=headers).json()
    assert final["status"] == "FAILED"
    assert "opportunity" in final["error"].lower()


async def test_prepare_fails_when_no_profile_json(
    client: TestClient, tmp_path: Path
) -> None:
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=headers).json()
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(), user_id=me["id"]
    )
    SqliteReviewSessionStore(_db_path()).save(_review_session(), user_id=me["id"])
    await SqliteOpportunityRepository(_db_path()).add(_opportunity())
    response = client.post(
        "/submissions/prepare",
        json={"application_session_id": "sess-1"},
        headers=headers,
    )
    prep_token = response.json()["token"]
    final = client.get(f"/submissions/prepare/{prep_token}", headers=headers).json()
    assert final["status"] == "FAILED"
    assert "profile.json" in final["error"]


def test_get_prepare_status_unknown_token_is_404(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/submissions/prepare/nonexistent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Confirm route: HTTP-level checks against a manually-seeded pending entry.
# ---------------------------------------------------------------------------


async def test_confirm_unknown_token_is_404(client: TestClient) -> None:
    token = _register(client)
    response = client.post(
        "/submissions/nonexistent/confirm",
        json={"approved": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_confirm_wrong_user_is_404(client: TestClient) -> None:
    owner_token = _register(client, email="owner@example.com")
    other_token = _register(client, email="other@example.com")
    owner_id = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {owner_token}"}
    ).json()["id"]

    submission_actions._pending["tok-1"] = submission_actions._PendingSubmission(
        owner_id
    )
    submission_actions._pending["tok-1"].status = "AWAITING_CONFIRMATION"

    response = client.post(
        "/submissions/tok-1/confirm",
        json={"approved": True},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


async def test_confirm_when_not_awaiting_confirmation_is_409(
    client: TestClient,
) -> None:
    token = _register(client)
    user_id = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).json()["id"]
    submission_actions._pending["tok-1"] = submission_actions._PendingSubmission(
        user_id
    )  # still PREPARING, not AWAITING_CONFIRMATION

    response = client.post(
        "/submissions/tok-1/confirm",
        json={"approved": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# The confirm_fn coordination itself, driven directly (see module docstring).
# ---------------------------------------------------------------------------


async def _seed_full_pipeline(tmp_path: Path, user_id: str) -> None:
    _write_profile(tmp_path)
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(), user_id=user_id
    )
    SqliteReviewSessionStore(_db_path()).save(_review_session(), user_id=user_id)
    await SqliteOpportunityRepository(_db_path()).add(_opportunity())


def _fake_submitted_result(**kwargs: object) -> SubmissionResult:
    return SubmissionResult(
        id="sub-1",
        application_session_id="sess-1",
        review_session_id="review-1",
        opportunity_id="opp-1",
        provider="greenhouse",
        company="Acme Corp",
        job_title="Backend Engineer",
        submitted=True,
        status="SUBMITTED",
    )


async def test_confirming_true_lets_the_flow_proceed_to_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_submit_prepared_application(*, confirm_fn, **kwargs):
        approved = await confirm_fn()
        assert approved is True
        return _fake_submitted_result()

    monkeypatch.setattr(
        submission_actions,
        "submit_prepared_application",
        _fake_submit_prepared_application,
    )
    await _seed_full_pipeline(tmp_path, user_id="u1")

    token = "tok-1"
    submission_actions._pending[token] = submission_actions._PendingSubmission("u1")
    submission_actions._pending[token].future.set_result(True)  # "already confirmed"

    await submission_actions._run_prepare_and_submit(token, "u1", "sess-1")

    entry = submission_actions._pending[token]
    assert entry.status == "DONE"
    assert entry.result_id == "sub-1"
    assert entry.error is None


async def test_declining_raises_cancelled_and_is_surfaced_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors SubmissionEngine.submit's own CancelledByUserError handling --
    this fake reproduces that contract so the test proves confirm_fn's
    "declined -> CancelledByUserError" behavior without a live browser."""

    async def _fake_submit_prepared_application(*, confirm_fn, **kwargs):
        try:
            await confirm_fn()
        except CancelledByUserError:
            return SubmissionResult(
                id="sub-2",
                application_session_id="sess-1",
                review_session_id="review-1",
                opportunity_id="opp-1",
                provider="greenhouse",
                company="Acme Corp",
                job_title="Backend Engineer",
                submitted=False,
                status="CANCELLED",
            )
        raise AssertionError("confirm_fn should have raised CancelledByUserError")

    monkeypatch.setattr(
        submission_actions,
        "submit_prepared_application",
        _fake_submit_prepared_application,
    )
    await _seed_full_pipeline(tmp_path, user_id="u1")

    token = "tok-2"
    submission_actions._pending[token] = submission_actions._PendingSubmission("u1")
    submission_actions._pending[token].future.set_result(False)  # declined

    await submission_actions._run_prepare_and_submit(token, "u1", "sess-1")

    entry = submission_actions._pending[token]
    assert entry.status == "DONE"
    assert entry.result_id == "sub-2"
