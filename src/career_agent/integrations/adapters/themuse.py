"""The Muse adapter (Phase 48, ADR-0066).

``search()`` delegates to the existing, real, tested, keyless
:class:`~career_agent.plugins.sources.job_boards.TheMuseSource`.

The Muse is a job-board aggregator, not a native ATS -- no ``FormFiller``
exists for it and no capability has been verified, so all stay ``False``.
See :mod:`career_agent.integrations.adapters.remoteok` for the same
reasoning in more detail.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from career_agent.integrations.adapters.base import (
    AdapterCapabilities,
    BrowserAdapterMixin,
)
from career_agent.plugins.sources.job_boards import TheMuseSource

if TYPE_CHECKING:
    from career_agent.core.interfaces import HttpClient
    from career_agent.domain.models import Opportunity


class TheMuseAdapter(BrowserAdapterMixin):
    """Wraps :class:`TheMuseSource`; adds URL recognition + browser hooks."""

    provider = "themuse"
    capabilities = AdapterCapabilities()

    def __init__(self, *, client: HttpClient) -> None:
        """Configure with just an HTTP client -- the API is keyless."""
        self._source = TheMuseSource(client=client)

    def supports(self, url: str) -> bool:
        """Whether ``url`` is a The Muse posting."""
        return "themuse.com" in url.lower()

    async def search(self, *, since: datetime, **_: object) -> list[Opportunity]:
        """Delegates to :class:`TheMuseSource` -- see module docstring."""
        return await self._source.fetch(since)
