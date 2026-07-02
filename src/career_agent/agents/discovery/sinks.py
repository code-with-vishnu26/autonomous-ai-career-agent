"""Held-candidate sinks that surface the discovery discard pile (ADR-0013).

The :class:`BusHeldCandidateSink` bridges a source's held candidates onto the
event bus as ``CandidateHeld`` events, so the discard pile lands on the
project's visibility spine where a dashboard or the Learning engine can consume
it. Tests use the in-memory sink in ``storage.memory`` instead.
"""

from __future__ import annotations

from career_agent.core.bus import EventBus
from career_agent.core.events import CandidateHeld
from career_agent.domain.models import HeldCandidate


class BusHeldCandidateSink:
    """Publishes each held candidate as a ``CandidateHeld`` event."""

    def __init__(self, bus: EventBus, *, correlation_id: str) -> None:
        """Bind the sink to a bus and the correlation id of the discovery run."""
        self._bus = bus
        self._correlation_id = correlation_id

    async def record(self, held: HeldCandidate) -> None:
        """Publish ``held`` as a ``CandidateHeld`` event onto the bus."""
        await self._bus.publish(
            CandidateHeld(
                correlation_id=self._correlation_id,
                source=held.source,
                reason=held.reason,
                reference=held.reference,
                extraction_confidence=held.extraction_confidence,
            )
        )
