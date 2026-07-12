"""Phase 58 (ADR-0077): the `/notifications/*` Notification Center endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.api.app import create_app
from career_agent.api.dependencies import get_notification_store
from career_agent.api.rate_limit import auth_rate_limiter

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


def _seed_notification(client: TestClient, token: str) -> str:
    """No API creates notifications directly (they come from real events) --
    seed one straight through the store the app itself is wired to."""
    store = get_notification_store()
    user_id = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).json()["id"]
    from career_agent.agents.notifications.engine import NotificationEngine

    notification = NotificationEngine(store).create(
        user_id=user_id,
        type="SUCCESS",
        category="resume_prepared",
        title="Application prepared",
        message="Ready for review.",
    )
    return notification.id


def test_list_notifications_requires_authentication(client: TestClient) -> None:
    response = client.get("/notifications")
    assert response.status_code == 401


def test_list_notifications_returns_the_caller_own(client: TestClient) -> None:
    token = _register(client)
    _seed_notification(client, token)
    response = client.get(
        "/notifications", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["category"] == "resume_prepared"
    assert body[0]["read_at"] is None


def test_unread_endpoint_matches_unread_notifications(client: TestClient) -> None:
    token = _register(client)
    notification_id = _seed_notification(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    unread_before = client.get("/notifications/unread", headers=headers).json()
    assert len(unread_before) == 1

    client.post(
        "/notifications/read",
        json={"notification_id": notification_id},
        headers=headers,
    )
    unread_after = client.get("/notifications/unread", headers=headers).json()
    assert unread_after == []


def test_mark_read_sets_read_at(client: TestClient) -> None:
    token = _register(client)
    notification_id = _seed_notification(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/notifications/read",
        json={"notification_id": notification_id},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["read_at"] is not None


def test_mark_read_unknown_id_returns_404(client: TestClient) -> None:
    token = _register(client)
    response = client.post(
        "/notifications/read",
        json={"notification_id": "does-not-exist"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_mark_all_read_marks_every_unread(client: TestClient) -> None:
    token = _register(client)
    _seed_notification(client, token)
    _seed_notification(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/notifications/read-all", headers=headers)
    assert response.status_code == 200
    assert response.json()["marked"] == 2
    assert client.get("/notifications/unread", headers=headers).json() == []


def test_delete_notification_removes_it(client: TestClient) -> None:
    token = _register(client)
    notification_id = _seed_notification(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.delete(f"/notifications/{notification_id}", headers=headers)
    assert response.status_code == 204
    assert client.get("/notifications", headers=headers).json() == []


def test_delete_unknown_id_returns_404(client: TestClient) -> None:
    token = _register(client)
    response = client.delete(
        "/notifications/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_notifications_are_isolated_per_user(client: TestClient) -> None:
    token_a = _register(client, email="a@example.com")
    token_b = _register(client, email="b@example.com")
    _seed_notification(client, token_a)

    response_b = client.get(
        "/notifications", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response_b.json() == []


def test_user_cannot_mark_read_or_delete_another_user_notification(
    client: TestClient,
) -> None:
    token_a = _register(client, email="a@example.com")
    token_b = _register(client, email="b@example.com")
    notification_id = _seed_notification(client, token_a)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    read_response = client.post(
        "/notifications/read",
        json={"notification_id": notification_id},
        headers=headers_b,
    )
    assert read_response.status_code == 404

    delete_response = client.delete(
        f"/notifications/{notification_id}", headers=headers_b
    )
    assert delete_response.status_code == 404
