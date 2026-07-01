"""The seam under real load: three differently-shaped sources, one agent.

Greenhouse ({"jobs":[...]}, int ids, ISO updated_at), Lever (bare array, uuid
ids, epoch-ms createdAt), and Ashby ({"jobs":[...]}, uuid ids, explicit
isRemote) all register as plain OpportunitySource plugins and flow through one
DiscoveryAgent purely as events -- with no change to the OpportunitySource
contract to accommodate any of them.
"""

from __future__ import annotations

from career_agent.agents.discovery.agent import DiscoveryAgent
from career_agent.core.bus import EventBus
from career_agent.core.events import Event, OpportunityDiscovered
from career_agent.core.interfaces import OpportunitySource, Task
from career_agent.core.registry import PluginRegistry
from career_agent.plugins.sources.ashby import AshbySource
from career_agent.plugins.sources.greenhouse import GreenhouseSource
from career_agent.plugins.sources.lever import LeverSource
from career_agent.storage.memory import InMemoryOpportunityRepository
from tests._fakes import FakeHttpClient, load_fixture


def _wired() -> tuple[DiscoveryAgent, list[OpportunityDiscovered]]:
    registry = PluginRegistry()
    registry.register(
        OpportunitySource,
        "greenhouse",
        GreenhouseSource(
            ["acme"],
            client=FakeHttpClient(
                {"/boards/acme/jobs": load_fixture("greenhouse", "jobs.json")}
            ),
        ),
    )
    registry.register(
        OpportunitySource,
        "lever",
        LeverSource(
            ["acme"],
            client=FakeHttpClient(
                {"/postings/acme": load_fixture("lever", "postings.json")}
            ),
        ),
    )
    registry.register(
        OpportunitySource,
        "ashby",
        AshbySource(
            ["beta"],
            client=FakeHttpClient(
                {"/job-board/beta": load_fixture("ashby", "jobs.json")}
            ),
        ),
    )

    bus = EventBus()
    discovered: list[OpportunityDiscovered] = []

    async def collect(event: Event) -> None:
        assert isinstance(event, OpportunityDiscovered)
        discovered.append(event)

    bus.subscribe(OpportunityDiscovered, collect)
    agent = DiscoveryAgent(registry, bus, InMemoryOpportunityRepository())
    return agent, discovered


def _task() -> Task:
    return Task(task_type="discover", correlation_id="corr-1", payload={})


async def test_all_three_sources_flow_through_one_agent() -> None:
    agent, discovered = _wired()
    await agent.handle(_task())

    # 2 postings per fixture x 3 sources
    assert len(discovered) == 6
    assert all(e.correlation_id == "corr-1" for e in discovered)
    # every opportunity id is distinct (no cross-source id collision)
    assert len({e.opportunity_id for e in discovered}) == 6


async def test_re_polling_all_three_sources_yields_no_duplicates() -> None:
    agent, discovered = _wired()
    await agent.handle(_task())
    await agent.handle(_task())
    assert len(discovered) == 6  # dedup holds across every source
