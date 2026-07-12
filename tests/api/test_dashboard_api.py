"""Phase 54/56 (ADR-0072/0074): the Web Dashboard API.

Every ``/api/*`` route wraps a store the CLI already writes through; these
tests seed that same store directly (bypassing the CLI, same pattern
``tests/storage/*`` already uses) and assert the API returns exactly what
the store holds for the *authenticated caller* -- no transformation, no
new business logic to verify. ``client`` is pre-authenticated as
``TEST_USER_ID``; ``anonymous_client`` has no token, for the 401 tests.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.core.security import create_access_token, hash_password
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.review import ReviewSession
from career_agent.domain.submission import SubmissionResult
from career_agent.domain.user import User
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
    SqliteUserStore,
)

TEST_USER_ID = "u1"
_TEST_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _TEST_JWT_SECRET)


@pytest.fixture
def anonymous_client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def client(anonymous_client: TestClient) -> TestClient:
    SqliteUserStore(_db_path()).create(
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
    anonymous_client.headers.update({"Authorization": f"Bearer {token}"})
    return anonymous_client


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
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(), user_id=TEST_USER_ID
    )
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
    store.save(
        _review_session(id="review-1", approval_status="WAITING"), user_id=TEST_USER_ID
    )
    store.save(
        _review_session(id="review-2", approval_status="APPROVED"), user_id=TEST_USER_ID
    )
    response = client.get("/api/reviews")
    assert response.status_code == 200
    assert {r["id"] for r in response.json()} == {"review-1", "review-2"}


def test_reviews_pending_filters_to_waiting_only(client: TestClient) -> None:
    store = SqliteReviewSessionStore(_db_path())
    store.save(
        _review_session(id="review-1", approval_status="WAITING"), user_id=TEST_USER_ID
    )
    store.save(
        _review_session(id="review-2", approval_status="APPROVED"), user_id=TEST_USER_ID
    )
    response = client.get("/api/reviews/pending")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "review-1"


def test_submissions_reflects_the_store(client: TestClient) -> None:
    SqliteSubmissionResultStore(_db_path()).save(
        _submission_result(), user_id=TEST_USER_ID
    )
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
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(), user_id=TEST_USER_ID
    )
    SqliteReviewSessionStore(_db_path()).save(_review_session(), user_id=TEST_USER_ID)
    SqliteSubmissionResultStore(_db_path()).save(
        _submission_result(), user_id=TEST_USER_ID
    )
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


def test_settings_never_leaks_the_jwt_secret(client: TestClient) -> None:
    """The signing key itself must never appear in an API response.

    Leaking it would let a caller forge an access token for any user id
    -- the single most safety-critical secret this endpoint could expose.
    """
    response = client.get("/api/settings")
    body = response.json()
    assert "jwt_secret_key" not in body["values"]
    assert _TEST_JWT_SECRET not in response.text
    assert body["configured_secrets"]["jwt_secret_key"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/applications",
        "/api/reviews",
        "/api/reviews/pending",
        "/api/submissions",
        "/api/resume-variants",
        "/api/analytics/summary",
        "/api/settings",
        "/auth/me",
    ],
)
def test_protected_routes_reject_an_anonymous_caller(
    anonymous_client: TestClient, path: str
) -> None:
    response = anonymous_client.get(path)
    assert response.status_code == 401


def test_applications_never_returns_another_users_data(
    client: TestClient, anonymous_client: TestClient
) -> None:
    """Per-user isolation: a second account never sees the first's rows."""
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(id="mine"), user_id=TEST_USER_ID
    )
    SqliteApplicationSessionStore(_db_path()).save(
        _application_session(id="not-mine"), user_id="someone-else"
    )
    response = client.get("/api/applications")
    ids = {row["id"] for row in response.json()}
    assert ids == {"mine"}


def _iter_routes(app):
    """Yield every real endpoint route the app registers.

    FastAPI wraps ``include_router``-added routes in an internal
    ``_IncludedRouter`` that has no ``.methods`` of its own -- the real
    ``APIRoute`` objects live on ``.original_router.routes``. Recursing
    through that is what makes this a real structural check instead of a
    silent no-op (a flat ``for route in app.routes`` skips every included
    router's routes entirely on this FastAPI version).
    """
    for route in app.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from original_router.routes
        else:
            yield route


def test_dashboard_data_routes_are_get_only() -> None:
    """The `/api/*` dashboard-data routes cannot mutate anything.

    Structural proof, not a per-route check: enumerates every `/api/*`
    route the app actually registers and asserts none allows
    POST/PUT/PATCH/DELETE. This is what actually enforces "no
    discover/prepare/review/submit trigger reachable from the dashboard
    data API" (ADR-0072) -- not just docstrings. `/auth/*`/`/user/*`
    (Phase 56, ADR-0074) are a deliberate, separately-scoped exception --
    see `test_auth_and_user_are_the_only_write_capable_routers`.
    """
    app = create_app()
    checked_any = False
    for route in _iter_routes(app):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if methods is None or not path.startswith("/api/"):
            continue
        checked_any = True
        assert methods <= {"GET", "HEAD", "OPTIONS"}, (
            f"{path} allows {methods} -- the dashboard data API is read-only"
        )
    assert checked_any, "no /api/* routes were found -- the test found nothing to check"


def test_auth_and_user_are_the_only_write_capable_routers() -> None:
    """No route outside the named write-capable prefixes allows a mutating method.

    Phase 56 (ADR-0074) added two write-capable routers -- authentication
    and the caller's own account/preferences. Phase 57 (ADR-0075) adds a
    third, `/coach/*`, for the Career Coach's stateless LLM-backed
    endpoints (a real costed action, even though none of them write to a
    database). Phase 58 (ADR-0077) adds `/notifications/*` and
    `/notification-settings` -- read/mark-read/delete on the caller's own
    notifications and their own delivery preferences. This proves nothing
    else silently gained a POST/PUT/PATCH/DELETE.
    """
    app = create_app()
    for route in _iter_routes(app):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if methods is None:
            continue
        mutating = methods - {"GET", "HEAD", "OPTIONS"}
        if mutating:
            allowed = (
                path.startswith("/auth/")
                or path.startswith("/user/")
                or path.startswith("/coach/")
                or path.startswith("/notifications/")
                or path.startswith("/notification-settings")
            )
            assert allowed, f"{path} allows {mutating} outside the write boundary"


def test_dependencies_construct_settings_freshly_not_cached() -> None:
    """Guards against re-introducing an lru_cache that would go stale across
    tests/requests when DATABASE_PATH changes mid-process."""
    from career_agent.api import dependencies as deps_module

    src = inspect.getsource(deps_module)
    assert "lru_cache" not in src
