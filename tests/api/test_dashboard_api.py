"""Phase 54 (ADR-0072): the read-only Web Dashboard API.

Every route wraps a store the CLI already writes through; these tests seed
that same store directly (bypassing the CLI, same pattern
``tests/storage/*`` already uses) and assert the API returns exactly what
the store holds -- no transformation, no new business logic to verify.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.review import ReviewSession
from career_agent.domain.submission import SubmissionResult
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
)


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _db_path() -> Path:
    return Path("career_agent.db")


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
        "approval_status": "WAITING",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ReviewSession(**fields)


def _submission_result(**overrides: object) -> SubmissionResult:
    fields = {
        "id": "sub-1",
        "application_session_id": "sess-1",
        "review_session_id": "review-1",
        "opportunity_id": "opp-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "submitted": True,
        "status": "SUBMITTED",
    }
    fields.update(overrides)
    return SubmissionResult(**fields)


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_applications_reflects_the_store(client: TestClient) -> None:
    SqliteApplicationSessionStore(_db_path()).save(_application_session())
    response = client.get("/api/applications")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "sess-1"
    assert body[0]["company"] == "Acme Corp"


def test_applications_empty_store_returns_empty_list(client: TestClient) -> None:
    response = client.get("/api/applications")
    assert response.status_code == 200
    assert response.json() == []


def test_reviews_lists_every_review(client: TestClient) -> None:
    store = SqliteReviewSessionStore(_db_path())
    store.save(_review_session(id="review-1", approval_status="WAITING"))
    store.save(_review_session(id="review-2", approval_status="APPROVED"))
    response = client.get("/api/reviews")
    assert response.status_code == 200
    assert {r["id"] for r in response.json()} == {"review-1", "review-2"}


def test_reviews_pending_filters_to_waiting_only(client: TestClient) -> None:
    store = SqliteReviewSessionStore(_db_path())
    store.save(_review_session(id="review-1", approval_status="WAITING"))
    store.save(_review_session(id="review-2", approval_status="APPROVED"))
    response = client.get("/api/reviews/pending")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "review-1"


def test_submissions_reflects_the_store(client: TestClient) -> None:
    SqliteSubmissionResultStore(_db_path()).save(_submission_result())
    response = client.get("/api/submissions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "SUBMITTED"


def test_resume_variants_empty_store_returns_empty_list(client: TestClient) -> None:
    response = client.get("/api/resume-variants")
    assert response.status_code == 200
    assert response.json() == []


def test_analytics_summary_counts_by_status(client: TestClient) -> None:
    SqliteApplicationSessionStore(_db_path()).save(_application_session())
    SqliteReviewSessionStore(_db_path()).save(_review_session())
    SqliteSubmissionResultStore(_db_path()).save(_submission_result())
    response = client.get("/api/analytics/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["applications_by_status"] == {"READY_FOR_REVIEW": 1}
    assert body["reviews_by_status"] == {"WAITING": 1}
    assert body["submissions_by_status"] == {"SUBMITTED": 1}


def test_settings_redacts_secret_fields(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-appear")
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert "anthropic_api_key" not in body["values"]
    assert "sk-should-never-appear" not in response.text
    assert body["configured_secrets"]["anthropic_api_key"] is True


def test_settings_reports_unconfigured_secret_as_false(client: TestClient) -> None:
    response = client.get("/api/settings")
    body = response.json()
    assert body["configured_secrets"]["anthropic_api_key"] is False


def test_only_get_methods_are_registered() -> None:
    """The dashboard API cannot mutate anything -- every route is a GET.

    Structural proof, not a per-route check: enumerates every route the
    app actually registers and asserts none allows POST/PUT/PATCH/DELETE.
    This is what actually enforces "no discover/prepare/review/submit
    trigger reachable from the API" for this phase -- not just docstrings.
    """
    app = create_app()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if methods is None:
            continue
        assert methods <= {"GET", "HEAD", "OPTIONS"}, (
            f"{route.path} allows {methods} -- Phase 54 is read-only"
        )


def test_dependencies_construct_settings_freshly_not_cached() -> None:
    """Guards against re-introducing an lru_cache that would go stale across
    tests/requests when DATABASE_PATH changes mid-process."""
    from career_agent.api import dependencies as deps_module

    src = inspect.getsource(deps_module)
    assert "lru_cache" not in src
