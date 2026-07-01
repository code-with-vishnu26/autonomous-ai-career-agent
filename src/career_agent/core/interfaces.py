"""Core interfaces (ADR-0001, ADR-0004).

The typed contracts every agent and plugin implements against. These are
:class:`typing.Protocol` definitions, not base classes with logic -- Phase 2
defines shape only. Concrete implementations land in the phases that need
them (see ROADMAP.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from career_agent.core.events import Event
from career_agent.domain.models import (
    Application,
    Company,
    MasterProfile,
    Opportunity,
    TailoredResumeDraft,
    TruthfulnessResult,
)


class Task(BaseModel):
    """A unit of work the Planner dispatches to one capability agent."""

    task_type: str
    correlation_id: str
    payload: dict[str, object]


@runtime_checkable
class AgentBase(Protocol):
    """The shape every capability agent must expose to the Planner.

    Per ADR-0001's design principles: single responsibility, stateless where
    possible, and reachable only through this one method -- an agent never
    exposes anything else for another agent (or the Planner) to call.
    """

    name: str

    async def handle(self, task: Task) -> None:
        """Perform ``task``, then return -- results/failures surface as events."""
        ...


# The plugin registry itself is a concrete class, not a Protocol -- see
# :mod:`career_agent.core.registry` (Phase 3, ADR-0004). Plugins do not
# implement a common ``PluginBase`` interface; they implement their
# extension-point protocol below (``SearchProvider``, ``ATSAdapter``, ...) and
# are registered via the ``@register`` decorator + ``discover()``.


# ---------------------------------------------------------------------------
# Search provider abstraction (ADR-0002).
# ---------------------------------------------------------------------------


class ProviderCapabilities(BaseModel):
    """What a search provider supports.

    Lets the Planner match capability to query instead of assuming.
    """

    supports_site_search: bool
    supports_freshness: bool
    supports_news: bool
    supports_semantic_search: bool
    supports_images: bool


class ProviderHealth(BaseModel):
    """Rolling health stats feeding the Planner's dynamic provider ranking."""

    latency_ms_p50: float
    success_rate: float
    cost_per_query: float


class SearchQuery(BaseModel):
    """A search request, carrying the requirements a provider must satisfy."""

    text: str
    requires_semantic: bool = False
    requires_freshness: bool = False
    site: str | None = None


class SearchResult(BaseModel):
    """One normalized result returned by a :class:`SearchProvider`."""

    url: str
    title: str
    snippet: str


@runtime_checkable
class SearchProvider(Protocol):
    """A pluggable web-search backend (ADR-0002).

    Capabilities are declared on the interface itself so the Planner can
    filter and rank eligible providers without any provider-specific
    knowledge.
    """

    capabilities: ProviderCapabilities

    async def health(self) -> ProviderHealth:
        """Return this provider's current rolling health/latency/cost stats."""
        ...

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Run ``query`` against this provider and return normalized results."""
        ...


# ---------------------------------------------------------------------------
# Opportunity sources and ATS adapters.
# ---------------------------------------------------------------------------


@runtime_checkable
class OpportunitySource(Protocol):
    """A pluggable opportunity feed (YC, Hacker News, career pages, ...)."""

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Return opportunities discovered since ``since``."""
        ...


@runtime_checkable
class ATSAdapter(Protocol):
    """A pluggable ATS integration (Greenhouse, Lever, Ashby, ...)."""

    ats_kind: str

    async def fetch_postings(self, company: Company) -> list[Opportunity]:
        """Return ``company``'s current postings from this ATS."""
        ...

    async def submit(self, application: Application) -> Event:
        """Submit ``application`` directly through this ATS's API."""
        ...


# ---------------------------------------------------------------------------
# Applying (ADR-0010) and truthfulness (ADR-0003).
# ---------------------------------------------------------------------------


@runtime_checkable
class Applicator(Protocol):
    """One interface for submitting an application.

    Tier selection (direct ATS API / driven browser / email-to-apply) is an
    internal strategy this implementation chooses between -- callers never
    see three separate interfaces for the three tiers (ADR-0010).
    """

    async def apply(self, application: Application) -> Event:
        """Submit ``application`` through whichever tier this implementation selects."""
        ...


@runtime_checkable
class ResumeGenerator(Protocol):
    """Tailors content into an unverified draft.

    Returns a :class:`~career_agent.domain.models.TailoredResumeDraft`, which
    deliberately has no :class:`TruthfulnessResult` attached -- a generator
    cannot approve its own output. See :class:`TruthfulnessGate`, a
    deliberately separate interface (ADR-0003).
    """

    async def tailor(
        self, opportunity: Opportunity, profile: MasterProfile
    ) -> TailoredResumeDraft:
        """Produce an unverified, structured draft for ``opportunity``."""
        ...


@runtime_checkable
class TruthfulnessGate(Protocol):
    """Verifies a draft against the master profile and renders a verdict (ADR-0003).

    Kept separate from :class:`ResumeGenerator` on purpose: a generator has
    no method that can mark its own output verified. Orchestration code (the
    Resume Agent) calls generator, then gate, as two distinct steps, and only
    assembles a :class:`~career_agent.domain.models.TailoredResume` after the
    gate has run.
    """

    async def verify(
        self, draft: TailoredResumeDraft, profile: MasterProfile
    ) -> TruthfulnessResult:
        """Verify every statement in ``draft`` against ``profile``."""
        ...


@runtime_checkable
class NotificationSink(Protocol):
    """A pluggable notification channel.

    Notifications are a cross-cutting concern, not a first-class agent
    (ADR-0001) -- this interface is how a plugin hooks into that concern.
    """

    async def notify(self, event: Event) -> None:
        """Deliver ``event`` to this sink's channel."""
        ...
