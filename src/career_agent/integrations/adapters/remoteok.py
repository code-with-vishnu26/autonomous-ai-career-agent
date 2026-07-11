"""RemoteOK adapter (Phase 48, ADR-0066).

``search()`` delegates to the existing, real, tested, keyless
:class:`~career_agent.plugins.sources.job_boards.RemoteOkSource`.

RemoteOK is a job-board aggregator, not a native ATS with its own apply
form -- no ``FormFiller`` exists for it, and none of the capability flags
below have ever been verified against a live posting, so all stay
``False`` (unverified, not confirmed absent). Aggregator postings
typically link out to the employer's own application page (often one of
the ATS platforms this framework already covers, or an external site
outside this framework's current scope).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from career_agent.integrations.adapters.base import (
    AdapterCapabilities,
    BrowserAdapterMixin,
)
from career_agent.plugins.sources.job_boards import RemoteOkSource

if TYPE_CHECKING:
    from career_agent.core.interfaces import HttpClient
    from career_agent.domain.models import Opportunity


class RemoteOkAdapter(BrowserAdapterMixin):
    """Wraps :class:`RemoteOkSource`; adds URL recognition + browser hooks."""

    provider = "remoteok"
    capabilities = AdapterCapabilities()

    def __init__(self, *, client: HttpClient) -> None:
        """Configure with just an HTTP client -- the API is keyless."""
        self._source = RemoteOkSource(client=client)

    def supports(self, url: str) -> bool:
        """Whether ``url`` is a RemoteOK posting (either known hostname)."""
        lowered = url.lower()
        return "remoteok.com" in lowered or "remoteok.io" in lowered

    async def search(self, *, since: datetime, **_: object) -> list[Opportunity]:
        """Delegates to :class:`RemoteOkSource` -- see module docstring."""
        return await self._source.fetch(since)
