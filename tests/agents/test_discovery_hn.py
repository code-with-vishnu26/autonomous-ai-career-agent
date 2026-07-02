"""Agent-level HN tests: dedup through the shared path, and a visible discard pile.

Confirms HN extraction feeds the *same* dedup path structured sources use (the
re-posted job #11 collapses onto #1 via the fingerprint, not a bypass), and that
held candidates surface as CandidateHeld events on the bus (the discard pile on
the visibility spine, not /dev/null).
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.agents.discovery.agent import DiscoveryAgent
from career_agent.agents.discovery.sinks import BusHeldCandidateSink
from career_agent.core.bus import EventBus
from career_agent.core.events import CandidateHeld, Event, OpportunityDiscovered
from career_agent.core.interfaces import OpportunitySource, Task
from career_agent.core.registry import PluginRegistry
from career_agent.plugins.sources.hn import HNSource
from career_agent.storage.memory import (
    InMemoryHeldCandidateSink,
    InMemoryOpportunityRepository,
)
from tests._fakes import FakeHttpClient, load_fixture

_THREAD_ID = 44444444
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _client() -> FakeHttpClient:
    fixture = load_fixture("hn", "whoishiring.json")
    responses: dict[str, object] = {f"/item/{_THREAD_ID}.json": fixture["thread"]}
    for comment_id, comment in fixture["comments"].items():
        responses[f"/item/{comment_id}.json"] = comment
    return FakeHttpClient(responses)


def _task() -> Task:
    return Task(task_type="discover", correlation_id="corr-1", payload={})


async def test_reposted_job_dedups_through_the_shared_fingerprint_path() -> None:
    """6 opportunities are emitted by the source (#1, #7x3, #10, #11), but #11
    is a re-post of #1, so the agent's repo dedup yields 5 discovery events --
    HN rides the same dedup path as structured sources, not a bypass."""
    registry = PluginRegistry()
    registry.register(
        OpportunitySource,
        "hn",
        HNSource(
            [_THREAD_ID], client=_client(), held_sink=InMemoryHeldCandidateSink()
        ),
    )
    bus = EventBus()
    discovered: list[OpportunityDiscovered] = []

    async def collect(event: Event) -> None:
        assert isinstance(event, OpportunityDiscovered)
        discovered.append(event)

    bus.subscribe(OpportunityDiscovered, collect)
    agent = DiscoveryAgent(registry, bus, InMemoryOpportunityRepository())

    await agent.handle(_task())
    assert len(discovered) == 5  # 6 emitted, #11 deduped onto #1
    assert len({e.opportunity_id for e in discovered}) == 5


async def test_held_candidates_surface_as_events_on_the_bus() -> None:
    """The discard pile lands on the visibility spine: a bus-backed sink turns
    each held candidate into a CandidateHeld event a dashboard/Learning engine
    can consume."""
    bus = EventBus()
    held_events: list[CandidateHeld] = []

    async def collect(event: Event) -> None:
        assert isinstance(event, CandidateHeld)
        held_events.append(event)

    bus.subscribe(CandidateHeld, collect)
    sink = BusHeldCandidateSink(bus, correlation_id="corr-1")
    source = HNSource([_THREAD_ID], client=_client(), held_sink=sink)

    await source.fetch(_EPOCH)

    # the 8 held archetypes (#2-#6, #8, #9, #12) each produce one event
    assert len(held_events) == 8
    assert {e.source for e in held_events} == {"hn"}
    assert all(e.extraction_confidence < 0.5 for e in held_events)
    assert {e.reason for e in held_events} == {
        "not_a_posting",
        "seeking_work",
        "ambiguous_parse",
        "below_threshold",
    }
