"""Phase 61 (ADR-0079): correlation IDs and the global exception handler.

Uses a throwaway router mounted onto the real app to exercise an unhandled
exception -- every real route already has its own explicit error handling
(auth failures, 404s, validation), so there is no existing route that
raises unexpectedly on purpose.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from career_agent.api.app import create_app

_TEST_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _TEST_JWT_SECRET)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def client_with_boom_route() -> TestClient:
    """A client whose app has one extra route that always raises."""
    app = create_app()
    router = APIRouter()

    @router.get("/__test_boom")
    def boom() -> None:
        raise ValueError("simulated failure")

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_response_carries_a_generated_request_id(client: TestClient) -> None:
    response = client.get("/health")
    request_id = response.headers.get("x-request-id")
    assert request_id
    # A real UUID4, not an empty placeholder.
    assert len(request_id) == 36


def test_response_reuses_a_caller_supplied_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "caller-chosen-id"})
    assert response.headers["x-request-id"] == "caller-chosen-id"


def test_two_requests_get_different_generated_ids(client: TestClient) -> None:
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]
    assert first != second


def test_unhandled_exception_returns_safe_json_with_request_id(
    client_with_boom_route: TestClient,
) -> None:
    response = client_with_boom_route.get("/__test_boom")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"]
    # Never leaks the exception message or a traceback fragment.
    assert "simulated failure" not in response.text
    assert "ValueError" not in response.text


def test_unhandled_exception_response_carries_the_same_request_id_as_the_request(
    client_with_boom_route: TestClient,
) -> None:
    response = client_with_boom_route.get(
        "/__test_boom", headers={"X-Request-ID": "trace-me-123"}
    )
    assert response.headers["x-request-id"] == "trace-me-123"
    assert response.json()["request_id"] == "trace-me-123"


def test_existing_http_exceptions_are_unaffected(client: TestClient) -> None:
    """A route that already raises HTTPException keeps its own shape/status."""
    response = client.get("/api/applications")
    assert response.status_code == 401
    assert "request_id" not in response.json()
