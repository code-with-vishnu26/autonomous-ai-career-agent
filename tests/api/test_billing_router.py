"""Phase 60 (ADR-0078): the `/billing/*` endpoints -- no Stripe."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.rate_limit import auth_rate_limiter
from career_agent.domain.billing import PLANS

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


def _register(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    return response.json()["access_token"]


def _my_org_id(client: TestClient, token: str) -> str:
    response = client.get(
        "/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()[0]["id"]


def test_list_plans_requires_no_authentication(client: TestClient) -> None:
    response = client.get("/billing/plans")
    assert response.status_code == 200
    assert {plan["id"] for plan in response.json()} == set(PLANS.keys())


def test_get_subscription_defaults_to_free(client: TestClient) -> None:
    token = _register(client)
    org_id = _my_org_id(client, token)
    response = client.get(
        f"/billing/{org_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["plan_id"] == "free"


def test_get_subscription_requires_membership(client: TestClient) -> None:
    owner_token = _register(client, email="owner@example.com")
    org_id = _my_org_id(client, owner_token)
    other_token = _register(client, email="other@example.com")

    response = client.get(
        f"/billing/{org_id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert response.status_code == 404


def test_checkout_requires_manage_billing_permission(client: TestClient) -> None:
    owner_token = _register(client, email="owner2@example.com")
    org_id = _my_org_id(client, owner_token)
    other_token = _register(client, email="other2@example.com")

    response = client.post(
        f"/billing/{org_id}/checkout",
        json={"plan_id": "pro"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


def test_checkout_activates_the_plan_immediately(client: TestClient) -> None:
    token = _register(client)
    org_id = _my_org_id(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/billing/{org_id}/checkout", json={"plan_id": "pro"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["subscription"]["plan_id"] == "pro"
    assert "checkout_url" in response.json()

    subscription = client.get(f"/billing/{org_id}", headers=headers).json()
    assert subscription["plan_id"] == "pro"


def test_usage_includes_a_live_seat_count(client: TestClient) -> None:
    token = _register(client)
    org_id = _my_org_id(client, token)
    response = client.get(
        f"/billing/{org_id}/usage", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    seats = next(m for m in response.json() if m["metric"] == "seats")
    assert seats["count"] == 1
