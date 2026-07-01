"""Tests for career_agent.core.bus."""

from __future__ import annotations

from career_agent.core.bus import EventBus, HandlerError
from career_agent.core.events import (
    ApplicationSubmitted,
    Event,
    OpportunityDiscovered,
    TruthfulnessRejected,
)


def _discovered() -> OpportunityDiscovered:
    return OpportunityDiscovered(
        correlation_id="c1", opportunity_id="opp-1", source="greenhouse"
    )


async def test_subscriber_receives_published_event() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(OpportunityDiscovered, handler)
    event = _discovered()
    errors = await bus.publish(event)

    assert received == [event]
    assert errors == []


async def test_non_subscribers_do_not_receive_the_event() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(ApplicationSubmitted, handler)  # different type
    await bus.publish(_discovered())

    assert received == []


async def test_subscribing_to_base_event_receives_all_events() -> None:
    """A handler on the Event base type is a firehose -- it sees every event,
    which is how cross-chain logging/tracing subscribes."""
    bus = EventBus()
    seen: list[str] = []

    async def audit(event: Event) -> None:
        seen.append(event.event_type)

    bus.subscribe(Event, audit)
    await bus.publish(_discovered())
    await bus.publish(
        ApplicationSubmitted(
            correlation_id="c1", application_id="app-1", tier_used="ats_api"
        )
    )

    assert seen == ["OpportunityDiscovered", "ApplicationSubmitted"]


async def test_handlers_run_in_subscription_order() -> None:
    bus = EventBus()
    order: list[int] = []

    async def first(event: Event) -> None:
        order.append(1)

    async def second(event: Event) -> None:
        order.append(2)

    bus.subscribe(OpportunityDiscovered, first)
    bus.subscribe(OpportunityDiscovered, second)
    await bus.publish(_discovered())

    assert order == [1, 2]


async def test_a_failing_handler_does_not_stop_the_others() -> None:
    """Error isolation: one subscriber raising must not prevent delivery to
    the rest. The failure is captured and returned, not propagated."""
    bus = EventBus()
    delivered: list[str] = []
    reported: list[HandlerError] = []
    bus.on_handler_error = reported.append

    async def boom(event: Event) -> None:
        raise RuntimeError("subscriber blew up")

    async def still_runs(event: Event) -> None:
        delivered.append("ok")

    bus.subscribe(OpportunityDiscovered, boom)
    bus.subscribe(OpportunityDiscovered, still_runs)
    errors = await bus.publish(_discovered())

    assert delivered == ["ok"]  # the second handler still ran
    assert len(errors) == 1
    assert isinstance(errors[0].exception, RuntimeError)
    assert reported == errors  # on_handler_error saw the same failure


async def test_events_notify_they_do_not_gate() -> None:
    """A swallowed TruthfulnessRejected handler must not be able to weaken the
    block: the bus reports the failure but never raises, precisely because the
    truthfulness block is enforced inline on the Apply path, not via the bus
    (ADR-0003 / ADR-0005). This test documents that delivery is best-effort and
    therefore MUST NOT be a safety mechanism."""
    bus = EventBus()

    async def flaky_notifier(event: Event) -> None:
        raise RuntimeError("failed to send the rejection notification")

    bus.subscribe(TruthfulnessRejected, flaky_notifier)
    errors = await bus.publish(
        TruthfulnessRejected(
            correlation_id="c1", opportunity_id="opp-1", rejection_count=2
        )
    )

    # publish() completes normally and merely records the delivery failure;
    # nothing here could "un-reject" the application, because the rejection was
    # already enforced upstream before this notification was ever published.
    assert len(errors) == 1
    assert isinstance(errors[0].exception, RuntimeError)


async def test_end_to_end_registered_plugin_communicates_via_events() -> None:
    """Phase 3 'done when': a discovered plugin does work and the result flows
    to a subscriber purely through the event bus (no direct call between the
    two)."""
    from career_agent.core.interfaces import SearchProvider, SearchQuery
    from career_agent.core.registry import PluginRegistry, discover
    from career_agent.plugins import examples

    registry = PluginRegistry()
    discover(examples, registry)
    provider = registry.get(SearchProvider, "echo")

    bus = EventBus()
    audit: list[str] = []

    async def on_discovered(event: Event) -> None:
        assert isinstance(event, OpportunityDiscovered)
        audit.append(event.opportunity_id)

    bus.subscribe(OpportunityDiscovered, on_discovered)

    # the plugin produces a result; a (would-be) discovery agent turns it into
    # an event; the subscriber reacts -- the two never call each other directly
    results = await provider.search(SearchQuery(text="engineer"))
    await bus.publish(
        OpportunityDiscovered(
            correlation_id="c1",
            opportunity_id=results[0].url,
            source="echo",
        )
    )

    assert audit == ["https://example.invalid/echo"]
