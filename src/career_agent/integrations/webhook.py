"""Generic webhook delivery (Phase 58, ADR-0077).

Built on the existing :class:`~career_agent.core.interfaces.HttpClient`
port -- the same one every other real-network integration in this project
already depends on (``TelegramNotifier``, the discovery sources) -- not a
new HTTP client. A user-configured URL receives one JSON POST per
notification; Slack/Discord/Teams incoming-webhook URLs (each is just an
HTTPS POST endpoint) work through this unmodified, without this project
needing a Slack/Discord/Teams-specific SDK -- exactly the "only build
channels that have existing infrastructure" instruction this phase's
brief itself gives, read the other way: a generic webhook already *is*
that infrastructure for any service whose integration is "receive a JSON
POST."
"""

from __future__ import annotations

from career_agent.core.interfaces import HttpClient
from career_agent.domain.notification import Notification


class WebhookDeliveryError(Exception):
    """A real webhook POST attempt failed."""


class WebhookSender:
    """POSTs one JSON payload per notification to a user-configured URL."""

    def __init__(self, client: HttpClient) -> None:
        """Configure with the real HTTP client to POST through."""
        self._client = client

    async def send(self, *, url: str, notification: Notification) -> None:
        """POST ``notification`` as JSON.

        Raises :class:`WebhookDeliveryError` on any failure -- never
        returns having silently not sent anything.
        """
        payload = {
            "id": notification.id,
            "type": notification.type,
            "category": notification.category,
            "title": notification.title,
            "message": notification.message,
            "created_at": notification.created_at.isoformat(),
        }
        try:
            await self._client.post_json(url, json=payload)
        except Exception as exc:  # noqa: BLE001 -- any failure here must fail closed
            raise WebhookDeliveryError(
                f"Webhook POST to {url} failed: {type(exc).__name__}: {exc}"
            ) from exc
