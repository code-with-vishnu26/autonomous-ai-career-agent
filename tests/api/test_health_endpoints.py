"""Phase 59 (ADR-0076): /health, /ready, /metrics -- container probes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_is_ok_with_no_dependencies(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_health_still_works_unchanged(client: TestClient) -> None:
    """Phase 54's original route -- the frontend already calls this."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_is_ok_when_the_database_is_reachable(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


def test_ready_is_503_when_the_database_path_is_unwritable(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A database path whose parent cannot be created (a file standing where
    # a directory is needed) reproduces a real "not ready" condition.
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory")
    monkeypatch.setenv("DATABASE_PATH", str(blocker / "career_agent.db"))
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"].startswith("error")


def test_metrics_is_prometheus_text_format(client: TestClient) -> None:
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "career_agent_uptime_seconds" in response.text
    assert "career_agent_requests_total" in response.text
    assert 'status="2xx"' in response.text
