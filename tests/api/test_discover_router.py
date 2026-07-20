"""Phase 63 (ADR-0081): the `/discover` web-triggered Discover endpoints.

``POST /discover`` runs the background task synchronously under
``TestClient`` (Starlette awaits ``BackgroundTasks`` before the response
finishes sending) -- so these tests can assert the final ``COMPLETED``
state directly, without polling. ``build_discovery_sources`` is
monkeypatched to a fake source (mirroring ``tests/test_cli_discover.py``'s
own ``_FakeSource``) so no real network call ever happens.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.dependencies import get_opportunity_repository
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.domain.models import Opportunity, Provenance

_JWT_SECRET = "unit-test-secret-not-for-real-use"


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """The rate limiter is process-global (ADR-0074) -- reset it so an
    earlier test's attempts never count against a later test's budget."""
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


def _opp(opportunity_id: str) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="Acme Corp",
        title=f"Engineer {opportunity_id}",
        source="job_board",
        source_url=f"https://example.invalid/{opportunity_id}",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.invalid/api",
            extraction_confidence=1.0,
        ),
        ats_ref=opportunity_id,
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _FakeSource:
    async def fetch(self, since):
        return [_opp("a"), _opp("b")]


def _fake_sources(settings, preferences=None):
    return [("fake-board", _FakeSource())]


def test_discover_requires_authentication(client: TestClient) -> None:
    response = client.post("/discover", json={})
    assert response.status_code == 401


def test_trigger_discovery_returns_pending_immediately_without_the_patch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With zero configured sources it's a real (harmless) no-op run --
    proves the endpoint never requires the monkeypatch to respond."""
    for var in (
        "ARBEITNOW_ENABLED",
        "THEMUSE_ENABLED",
        "REMOTIVE_ENABLED",
        "REMOTEOK_ENABLED",
    ):
        monkeypatch.setenv(var, "false")
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/discover", json={"since_days": 3}, headers=headers)
    assert response.status_code == 202
    # The response body reflects the PENDING record as of the moment the
    # route returned -- BackgroundTasks run after the body is serialized,
    # so the final status is only visible via a follow-up poll.
    assert response.json()["status"] == "PENDING"

    final = client.get(f"/discover/{response.json()['id']}", headers=headers).json()
    assert final["status"] == "COMPLETED"
    assert final["new_count"] == 0
    assert final["source_labels"] == []


def test_trigger_discovery_persists_new_opportunities_and_reports_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "career_agent.api.routers.discover.build_discovery_sources", _fake_sources
    )
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/discover", json={}, headers=headers)
    assert response.status_code == 202
    run_id = response.json()["id"]

    final = client.get(f"/discover/{run_id}", headers=headers).json()
    assert final["status"] == "COMPLETED"
    assert final["new_count"] == 2
    assert final["source_labels"] == ["fake-board"]
    assert final["errors"] == []

    opportunities = client.get("/discover/opportunities", headers=headers).json()
    assert {o["opportunity"]["id"] for o in opportunities} == {"a", "b"}
    # No preferences configured yet -- Phase 70's "matches everything"
    # default classifies everything as an exact match (Phase 72).
    assert {o["relevance_tier"] for o in opportunities} == {"exact"}


def test_opportunities_are_classified_exact_vs_related_per_caller_preferences(
    client: TestClient,
) -> None:
    """Phase 72 (ADR-0090): the shared opportunity catalog is classified
    per-caller against their own configured role, not a static property of
    the opportunity itself."""
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        "/user/preferences",
        json={"preferred_titles": ["Software Developer"]},
        headers=headers,
    )

    async def _seed(repo) -> None:
        await repo.add(
            _opp("a").model_copy(update={"title": "Software Developer"})
        )
        await repo.add(
            _opp("b").model_copy(update={"title": "Backend Developer"})
        )
        await repo.add(_opp("c").model_copy(update={"title": "Barista"}))

    asyncio.run(_seed(get_opportunity_repository()))

    response = client.get("/discover/opportunities", headers=headers)
    assert response.status_code == 200
    by_id = {o["opportunity"]["id"]: o["relevance_tier"] for o in response.json()}
    assert by_id["a"] == "exact"
    assert by_id["b"] == "related"
    assert by_id["c"] == "none"


def test_get_run_status_reflects_the_completed_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "career_agent.api.routers.discover.build_discovery_sources", _fake_sources
    )
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    triggered = client.post("/discover", json={}, headers=headers).json()
    fetched = client.get(f"/discover/{triggered['id']}", headers=headers).json()
    assert fetched["id"] == triggered["id"]
    assert fetched["status"] == "COMPLETED"


def test_get_run_status_unknown_id_is_404(client: TestClient) -> None:
    token = _register(client)
    response = client.get(
        "/discover/nonexistent", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_run_status_never_leaks_across_users(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "career_agent.api.routers.discover.build_discovery_sources", _fake_sources
    )
    owner_token = _register(client, email="owner@example.com")
    other_token = _register(client, email="other@example.com")
    triggered = client.post(
        "/discover", json={}, headers={"Authorization": f"Bearer {owner_token}"}
    ).json()
    response = client.get(
        f"/discover/{triggered['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


def test_list_runs_returns_only_the_callers_own(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "career_agent.api.routers.discover.build_discovery_sources", _fake_sources
    )
    owner_token = _register(client, email="owner2@example.com")
    other_token = _register(client, email="other2@example.com")
    client.post(
        "/discover", json={}, headers={"Authorization": f"Bearer {owner_token}"}
    )
    owner_runs = client.get(
        "/discover/runs", headers={"Authorization": f"Bearer {owner_token}"}
    ).json()
    other_runs = client.get(
        "/discover/runs", headers={"Authorization": f"Bearer {other_token}"}
    ).json()
    assert len(owner_runs) == 1
    assert other_runs == []


def test_a_failing_source_is_recorded_but_does_not_fail_the_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _BrokenSource:
        async def fetch(self, since):
            raise RuntimeError("api down")

    def _mixed_sources(settings, preferences=None):
        return [("fake-board", _FakeSource()), ("broken", _BrokenSource())]

    monkeypatch.setattr(
        "career_agent.api.routers.discover.build_discovery_sources", _mixed_sources
    )
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/discover", json={}, headers=headers)
    run_id = response.json()["id"]
    final = client.get(f"/discover/{run_id}", headers=headers).json()
    assert final["status"] == "COMPLETED"
    assert final["new_count"] == 2
    assert final["errors"] == ["broken: api down"]
