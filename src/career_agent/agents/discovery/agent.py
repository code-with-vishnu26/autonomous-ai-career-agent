"""Discovery Agent (Phase 4a).

The first capability agent and the proof that the plugin registry + event bus
pay off. It owns exactly one job: pull opportunities from every registered
:class:`OpportunitySource`, deduplicate them, and announce the genuinely new
ones on the event bus. It never calls another agent and never imports a
concrete source -- sources arrive through the registry, results leave as
``OpportunityDiscovered`` events (ADR-0001, ADR-0005).
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.bus import EventBus
from career_agent.core.events import OpportunityDiscovered
from career_agent.core.interfaces import (
    OpportunityRepository,
    OpportunitySource,
    Task,
)
from career_agent.core.registry import PluginRegistry

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class DiscoveryAgent:
    """Coordinates opportunity sources; emits discovery events for new finds."""

    name = "discovery"

    def __init__(
        self,
        registry: PluginRegistry,
        bus: EventBus,
        repo: OpportunityRepository,
    ) -> None:
        """Wire the agent to its registry, event bus, and dedup repository."""
        self._registry = registry
        self._bus = bus
        self._repo = repo

    async def handle(self, task: Task) -> None:
        """Fetch from every registered source and emit events for new finds.

        Reads an optional ISO-8601 ``since`` from ``task.payload`` (defaulting
        to the epoch, i.e. "everything"). Each source is polled independently;
        a source that raises does not abort the others (best-effort discovery,
        mirroring the bus's error isolation). Only opportunities the repository
        accepts as new (dedup by :attr:`Opportunity.id`) produce an
        ``OpportunityDiscovered`` event, so re-polling never re-announces a
        known opportunity.
        """
        since = self._since_of(task)
        for source in self._registry.all(OpportunitySource):
            try:
                opportunities = await source.fetch(since)
            except Exception:  # noqa: BLE001 -- one bad source must not stop the rest
                continue
            for opportunity in opportunities:
                if await self._repo.add(opportunity):
                    await self._bus.publish(
                        OpportunityDiscovered(
                            correlation_id=task.correlation_id,
                            opportunity_id=opportunity.id,
                            source=opportunity.source,
                        )
                    )

    @staticmethod
    def _since_of(task: Task) -> datetime:
        raw = task.payload.get("since")
        if isinstance(raw, str) and raw:
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                return _EPOCH
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return _EPOCH
