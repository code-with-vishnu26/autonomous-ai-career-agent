"""Notifications: Telegram Bot API with ntfy.sh fallback (Phase 16, ADR-0040).

A tiny ``Notifier`` port (``notify(title, message)``) with two real
implementations, both driven through the existing
:class:`~career_agent.core.interfaces.HttpClient` port so tests replay
fixtures with zero network:

- :class:`TelegramNotifier` -- Bot API ``sendMessage``. The bot token is
  part of Telegram's URL scheme by API design; it is never logged,
  never recorded into any stored data, and never included in error
  text (verified by test).
- :class:`NtfyNotifier` -- the zero-setup fallback: JSON publish to an
  ntfy.sh topic. No account, no token; the topic name is the only secret
  (documented plainly).

Notification *sending* follows the events-notify-never-gate rule
(ADR-0005): :class:`NotifyingSubscriber` subscribes to bus events
(pause needs attention, application failed, outcome recorded) and a
notification failure is logged and swallowed -- a dead Telegram bot must
never block or fail a submission flow. Deliveries are best-effort
telemetry, not control flow.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from career_agent.core.events import (
    ApplicationFailed,
    Event,
    HumanActionRequired,
    OutcomeRecorded,
)
from career_agent.core.interfaces import HttpClient

logger = logging.getLogger(__name__)


@runtime_checkable
class Notifier(Protocol):
    """Send one short, human-facing notification. Best-effort by contract."""

    async def notify(self, title: str, message: str) -> None:
        """Deliver the notification; raise on failure (caller decides policy)."""
        ...


class TelegramNotifier:
    """Telegram Bot API notifier -- config: bot token + chat id."""

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        client: HttpClient,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        """Configure with a bot token and the destination chat id."""
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def notify(self, title: str, message: str) -> None:
        """Send via ``sendMessage``. The token never appears in errors/logs."""
        url = f"{self._base_url}/bot{self._bot_token}/sendMessage"
        try:
            await self._client.post_json(
                url,
                json={"chat_id": self._chat_id, "text": f"{title}\n{message}"},
            )
        except Exception as exc:
            # Re-raise with the token structurally absent from the message:
            # the original exception may carry the URL, so it is not chained.
            raise RuntimeError(
                f"Telegram sendMessage failed: {type(exc).__name__} "
                f"(token elided)"
            ) from None


class NtfyNotifier:
    """ntfy.sh notifier -- the zero-setup fallback (topic name is the secret)."""

    def __init__(
        self,
        *,
        topic: str,
        client: HttpClient,
        base_url: str = "https://ntfy.sh",
    ) -> None:
        """Configure with an ntfy topic."""
        self._topic = topic
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def notify(self, title: str, message: str) -> None:
        """JSON-publish to the configured topic."""
        await self._client.post_json(
            self._base_url,
            json={"topic": self._topic, "title": title, "message": message},
        )


class NotifyingSubscriber:
    """Translate bus events into notifications -- notify, never gate.

    A delivery failure is logged and swallowed here by design (ADR-0005):
    the bus already isolates subscriber errors, and a broken notifier
    must never affect the flow that emitted the event.
    """

    def __init__(self, notifier: Notifier) -> None:
        """Wrap ``notifier`` for use as a bus subscriber."""
        self._notifier = notifier

    async def __call__(self, event: Event) -> None:
        """Handle one bus event; never raises."""
        rendered = _render(event)
        if rendered is None:
            return
        title, message = rendered
        try:
            await self._notifier.notify(title, message)
        except Exception as exc:  # noqa: BLE001 -- notify, never gate
            logger.warning("notification not delivered: %s", exc)


def _render(event: Event) -> tuple[str, str] | None:
    if isinstance(event, HumanActionRequired):
        return (
            "Action needed",
            f"Application {event.application_id}: {event.reason} -- the run "
            f"is paused until you act.",
        )
    if isinstance(event, ApplicationFailed):
        return (
            "Application failed",
            f"Application {event.application_id} failed at tier "
            f"{event.tier_attempted} ({event.error_category}).",
        )
    if isinstance(event, OutcomeRecorded):
        return (
            "Outcome recorded",
            f"Application {event.application_id}: {event.kind}.",
        )
    return None
