"""In-memory :class:`OpportunityRepository` for Phase 4a.

A faithful, minimal implementation of the repository contract in
:mod:`career_agent.core.interfaces`: it exposes exactly ``add`` and ``get`` and
nothing more, so the later SQLite implementation is a drop-in replacement with
no interface to renegotiate. State lives in a private dict; there are no extra
convenience methods (``all``, ``count``, ``clear``) that the persistent store
would not also have -- tests assert behavior through the contract and through
emitted events, not through repository internals.
"""

from __future__ import annotations

from career_agent.domain.identity import canonical_fingerprint
from career_agent.domain.models import HeldCandidate, Opportunity


class InMemoryOpportunityRepository:
    """Deduplicating opportunity store: two-key identity (ADR-0014)."""

    def __init__(self) -> None:
        """Create an empty repository."""
        self._by_id: dict[str, Opportunity] = {}
        self._fingerprints: set[str] = set()

    async def add(self, opportunity: Opportunity) -> bool:
        """Store ``opportunity`` if it is new; return whether it was new.

        Dedup is two-key (ADR-0014): an exact primary-id match is always a
        duplicate, and a *non-authoritative* opportunity (one with no native
        source id, ``ats_ref is None`` -- e.g. Hacker News, later web search)
        whose fingerprint matches a known job is a cross-source duplicate. Two
        *authoritative* opportunities (native ``ats_ref``) that share a
        fingerprint are kept separate, since the source itself says they are
        distinct reqs -- no over-merge.
        """
        if opportunity.id in self._by_id:
            return False
        fingerprint = canonical_fingerprint(
            opportunity.canonical_company, opportunity.title, opportunity.location
        )
        authoritative = opportunity.ats_ref is not None
        if not authoritative and fingerprint in self._fingerprints:
            return False
        self._by_id[opportunity.id] = opportunity
        self._fingerprints.add(fingerprint)
        return True

    async def get(self, opportunity_id: str) -> Opportunity | None:
        """Return the stored opportunity with ``opportunity_id``, or ``None``."""
        return self._by_id.get(opportunity_id)


class InMemoryHeldCandidateSink:
    """In-memory :class:`HeldCandidateSink` (ADR-0013).

    Keeps held candidates in a list so tests can assert exactly which archetype
    produced which held reason. The production sink publishes ``CandidateHeld``
    events to the bus instead (see ``agents.discovery.sinks``); both satisfy the
    same contract.
    """

    def __init__(self) -> None:
        """Create an empty sink."""
        self.held: list[HeldCandidate] = []

    async def record(self, held: HeldCandidate) -> None:
        """Append ``held`` to the recorded discard pile."""
        self.held.append(held)
