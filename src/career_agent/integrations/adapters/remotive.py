"""Remotive adapter (Phase 48, ADR-0066).

``search()`` delegates to the existing, real, tested, keyless
:class:`~career_agent.plugins.sources.job_boards.RemotiveSource`.

Remotive is a job-board aggregator, not a native ATS -- no ``FormFiller``
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
from career_agent.plugins.sources.job_boards import RemotiveSource

if TYPE_CHECKING:
    from career_agent.core.interfaces import HttpClient
    from career_agent.domain.models import Opportunity


class RemotiveAdapter(BrowserAdapterMixin):
    """Wraps :class:`RemotiveSource`; adds URL recognition + browser hooks."""

    provider = "remotive"
    capabilities = AdapterCapabilities()

    def __init__(self, *, client: HttpClient) -> None:
        """Configure with just an HTTP client -- the API is keyless."""
        self._source = RemotiveSource(client=client)

    def supports(self, url: str) -> bool:
        """Whether ``url`` is a Remotive posting."""
        return "remotive.com" in url.lower()

    async def search(self, *, since: datetime, **_: object) -> list[Opportunity]:
        """Delegates to :class:`RemotiveSource` -- see module docstring."""
        return await self._source.fetch(since)
