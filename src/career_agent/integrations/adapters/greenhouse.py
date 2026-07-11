"""Greenhouse adapter (Phase 48, ADR-0066).

``search()`` delegates to the existing, real, tested
:class:`~career_agent.plugins.sources.greenhouse.GreenhouseSource` (a
public JSON API) rather than scraping postings through a browser --
faster, more reliable, and already exercised by ``career-agent discover``.

Capabilities grounded in real evidence:
:class:`~career_agent.agents.apply.form_fillers.GreenhouseFormFiller` is
this project's one *fully verified* application-form filler, confirming
Greenhouse's resume field (``#resume_text``) is a manual **text** field,
not a file upload -- so ``supports_resume_upload=False`` here reflects
verified reality, not an unset default. No verified evidence exists for a
cover-letter field or an "easy apply" flow, so both stay ``False``
(unverified, not confirmed absent).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from career_agent.integrations.adapters.base import (
    AdapterCapabilities,
    BrowserAdapterMixin,
)
from career_agent.plugins.sources.greenhouse import GreenhouseSource

if TYPE_CHECKING:
    from career_agent.core.interfaces import HttpClient
    from career_agent.domain.models import Opportunity


class GreenhouseAdapter(BrowserAdapterMixin):
    """Wraps :class:`GreenhouseSource`; adds URL recognition + browser hooks."""

    provider = "greenhouse"
    capabilities = AdapterCapabilities(
        supports_resume_upload=False,
        supports_cover_letter_upload=False,
        supports_easy_apply=False,
    )

    def __init__(self, boards: list[str], *, client: HttpClient) -> None:
        """Configure with the Greenhouse board tokens to search.

        Also takes an HTTP client -- the same constructor shape
        ``build_discovery_sources`` already uses for every keyword-driven
        source.
        """
        self._source = GreenhouseSource(boards, client=client)

    def supports(self, url: str) -> bool:
        """Whether ``url`` is a Greenhouse posting."""
        return "boards.greenhouse.io" in url.lower()

    async def search(self, *, since: datetime, **_: object) -> list[Opportunity]:
        """Delegates to :class:`GreenhouseSource` -- see module docstring."""
        return await self._source.fetch(since)
