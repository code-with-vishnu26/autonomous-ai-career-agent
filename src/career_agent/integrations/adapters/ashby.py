"""Ashby adapter (Phase 48, ADR-0066).

``search()`` delegates to the existing, real, tested
:class:`~career_agent.plugins.sources.ashby.AshbySource` (a public JSON
API) -- discovery works fine for Ashby.

Capabilities are a different story:
:class:`~career_agent.agents.apply.form_fillers.AshbyFormFiller` is an
explicit stub (Ashby's application forms are per-company-configurable,
fields identified by an internal ``path`` rather than a stable public DOM
contract; no live posting's real selectors have been verified). This
adapter's capabilities therefore stay entirely unverified (``False``
everywhere) -- not confirmed absent, simply not yet known, the same
distinction ``AshbyFormFiller`` itself draws.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from career_agent.integrations.adapters.base import (
    AdapterCapabilities,
    BrowserAdapterMixin,
)
from career_agent.plugins.sources.ashby import AshbySource

if TYPE_CHECKING:
    from career_agent.core.interfaces import HttpClient
    from career_agent.domain.models import Opportunity


class AshbyAdapter(BrowserAdapterMixin):
    """Wraps :class:`AshbySource`; adds URL recognition + browser hooks."""

    provider = "ashby"
    capabilities = AdapterCapabilities(
        supports_resume_upload=False,
        supports_cover_letter_upload=False,
        supports_easy_apply=False,
    )

    def __init__(self, boards: list[str], *, client: HttpClient) -> None:
        """Configure with the Ashby job-board names to search.

        Also takes an HTTP client, injected for tests.
        """
        self._source = AshbySource(boards, client=client)

    def supports(self, url: str) -> bool:
        """Whether ``url`` is an Ashby posting."""
        return "jobs.ashbyhq.com" in url.lower()

    async def search(self, *, since: datetime, **_: object) -> list[Opportunity]:
        """Delegates to :class:`AshbySource` -- see module docstring."""
        return await self._source.fetch(since)
