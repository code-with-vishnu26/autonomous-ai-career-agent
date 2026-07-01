"""In-process event bus: the sole inter-agent communication channel (ADR-0005).

Publish/subscribe with these deliberately-scoped delivery guarantees for the
single-user, single-process MVP:

- **Scope:** in-process, single process.
- **Delivery:** at-most-once, best-effort. No persistence, no retry, no ack.
- **Durability:** none -- a crash loses in-flight events. SQLite remains the
  system of record, not the message path.
- **Ordering:** FIFO per :meth:`EventBus.publish`; handlers run in
  subscription order.
- **Isolation:** one handler raising does NOT stop the others -- the
  exception is captured as a :class:`HandlerError`, reported, and dispatch
  continues so a flaky subscriber cannot wedge the bus.
- **Concurrency:** handlers are awaited sequentially (deterministic first;
  concurrent dispatch is a later opt-in).
- **Replay:** unsupported (see ADR-0005's durable-broker revisit criteria).

The interface is transport-agnostic, so a durable/out-of-process backend can
replace the in-process implementation later without changing any publisher or
subscriber.

Events notify; they do not gate
-------------------------------
Because delivery is best-effort and handler errors are swallowed, the bus
MUST NOT be the mechanism that enforces a safety-critical decision. In
particular the truthfulness block (ADR-0003) is enforced *synchronously and
inline* on the Apply path (generator -> gate -> hard stop when not approved);
a ``TruthfulnessRejected`` event is only a *notification of a decision already
enforced*, never the thing that enforces it. If a rejection notification's
handler throws and is swallowed here, the block has still already happened
upstream. Never move a safety-critical block onto event delivery.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from career_agent.core.events import Event

Handler = Callable[[Event], Awaitable[None]]


@dataclass
class HandlerError:
    """Captures a subscriber that raised while handling an event.

    Collected and returned by :meth:`EventBus.publish` (and passed to the
    bus's ``on_handler_error`` reporter) so a failing subscriber is visible
    without breaking delivery to the others.
    """

    event: Event
    handler: Handler
    exception: Exception


@dataclass
class EventBus:
    """A minimal in-process publish/subscribe event bus.

    Subscribe a handler to a concrete event type, or to the :class:`Event`
    base type to receive *every* event (useful for structured logging and
    tracing across the whole Discover -> Decide -> Apply -> Learn chain).
    """

    on_handler_error: Callable[[HandlerError], None] | None = None
    _subscribers: dict[type[Event], list[Handler]] = field(
        default_factory=dict, init=False, repr=False
    )

    def subscribe(self, event_type: type[Event], handler: Handler) -> None:
        """Register ``handler`` to receive events of ``event_type``.

        Subscribing to :class:`Event` itself receives all events, since every
        event is a subclass of ``Event``.
        """
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Event) -> list[HandlerError]:
        """Dispatch ``event`` to every matching subscriber, then return.

        A subscriber matches if it subscribed to ``type(event)`` or to any of
        its ``Event`` superclasses. Handlers run sequentially in subscription
        order; exceptions are captured as :class:`HandlerError` (reported via
        ``on_handler_error`` if set) and never abort the remaining handlers.
        Returns the list of errors that occurred (empty when all succeeded).
        """
        errors: list[HandlerError] = []
        for event_type in self._matching_types(type(event)):
            for handler in self._subscribers.get(event_type, ()):
                try:
                    await handler(event)
                except Exception as exc:  # noqa: BLE001 -- isolation is the point
                    handler_error = HandlerError(
                        event=event, handler=handler, exception=exc
                    )
                    errors.append(handler_error)
                    if self.on_handler_error is not None:
                        self.on_handler_error(handler_error)
        return errors

    @staticmethod
    def _matching_types(event_type: type[Event]) -> list[type[Event]]:
        """Return ``event_type`` plus each ``Event`` superclass, most-derived first."""
        return [
            cls
            for cls in event_type.__mro__
            if isinstance(cls, type) and issubclass(cls, Event)
        ]
