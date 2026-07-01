"""End-to-end tests for the Discovery Agent (Phase 4a's proof slice).

Wires a real (fixture-backed) Greenhouse source through the plugin registry,
runs the agent, and asserts that discoveries flow out purely as events -- the
source and any subscriber never call each other directly.
"""

from __future__ import annotations

from datetime import datetime

from career_agent.agents.discovery.agent import DiscoveryAgent
from career_agent.core.bus import EventBus
from career_agent.core.events import Event, OpportunityDiscovered
from career_agent.core.interfaces import OpportunitySource, Task
from career_agent.core.registry import PluginRegistry
from career_agent.plugins.sources.greenhouse import GreenhouseSource
from career_agent.storage.memory import InMemoryOpportunityRepository
from tests._fakes import FakeHttpClient, load_fixture


def _wired() -> tuple[DiscoveryAgent, EventBus, list[OpportunityDiscovered]]:
    registry = PluginRegistry()
    client = FakeHttpClient(
        {"/boards/acme/jobs": load_fixture("greenhouse", "jobs.json")}
    )
    # config-bearing source registered explicitly by the composition root
    registry.register(
        OpportunitySource, "greenhouse", GreenhouseSource(["acme"], client=client)
    )

    bus = EventBus()
    discovered: list[OpportunityDiscovered] = []

    async def collect(event: Event) -> None:
        assert isinstance(event, OpportunityDiscovered)
        discovered.append(event)

    bus.subscribe(OpportunityDiscovered, collect)
    agent = DiscoveryAgent(registry, bus, InMemoryOpportunityRepository())
    return agent, bus, discovered


def _task() -> Task:
    return Task(task_type="discover", correlation_id="corr-1", payload={})


async def test_discovery_emits_one_event_per_new_opportunity() -> None:
    agent, _bus, discovered = _wired()
    await agent.handle(_task())

    assert len(discovered) == 2
    assert all(e.source == "ats_api" for e in discovered)
    assert all(e.correlation_id == "corr-1" for e in discovered)


async def test_re_polling_does_not_re_announce_known_opportunities() -> None:
    """The dedup requirement: running discovery twice against the same board
    yields events only the first time."""
    agent, _bus, discovered = _wired()
    await agent.handle(_task())
    first_count = len(discovered)
    await agent.handle(_task())  # same source, same jobs
    assert first_count == 2
    assert len(discovered) == 2  # no new events on the second poll


async def test_since_is_honored_from_task_payload() -> None:
    agent, _bus, discovered = _wired()
    task = Task(
        task_type="discover",
        correlation_id="corr-1",
        payload={"since": "2026-06-01T00:00:00+00:00"},
    )
    await agent.handle(task)
    assert len(discovered) == 1  # only the June posting passes the cutoff


async def test_a_failing_source_does_not_stop_the_others() -> None:
    """Best-effort discovery: one source raising must not prevent a healthy
    source's opportunities from being announced."""
    agent, _bus, discovered = _wired()

    class _BoomSource:
        async def fetch(self, since: datetime) -> list:
            raise RuntimeError("source is down")

    agent._registry.register(OpportunitySource, "boom", _BoomSource())
    await agent.handle(_task())

    assert len(discovered) == 2  # greenhouse still delivered despite boom failing
