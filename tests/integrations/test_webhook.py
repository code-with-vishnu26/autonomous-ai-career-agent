"""Phase 58 (ADR-0077): WebhookSender -- one JSON POST per notification."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.domain.notification import Notification
from career_agent.integrations.webhook import WebhookDeliveryError, WebhookSender
from tests._fakes import FakeHttpClient


def _notification(**overrides: object) -> Notification:
    fields: dict[object, object] = {
        "id": "n1",
        "type": "SUCCESS",
        "category": "resume_prepared",
        "title": "Prepared",
        "message": "Ready for review.",
        "created_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return Notification(**fields)


async def test_send_posts_notification_fields_as_json() -> None:
    client = FakeHttpClient(default={})
    sender = WebhookSender(client)
    notification = _notification()

    await sender.send(url="https://hooks.example.com/x", notification=notification)

    url, payload = client.post_calls[0]
    assert url == "https://hooks.example.com/x"
    assert payload["id"] == "n1"
    assert payload["category"] == "resume_prepared"
    assert payload["title"] == "Prepared"
    assert payload["message"] == "Ready for review."


async def test_send_raises_webhook_delivery_error_on_failure() -> None:
    class _Boom:
        async def post_json(self, url, *, json, headers=None):
            raise RuntimeError("connection refused")

        async def get_json(self, url, *, params=None, headers=None):
            raise NotImplementedError

    sender = WebhookSender(_Boom())
    with pytest.raises(WebhookDeliveryError):
        await sender.send(
            url="https://hooks.example.com/x", notification=_notification()
        )
