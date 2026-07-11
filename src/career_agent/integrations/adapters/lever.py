"""Lever adapter (Phase 48, ADR-0066).

``search()`` delegates to the existing, real, tested
:class:`~career_agent.plugins.sources.lever.LeverSource` (a public JSON
API) rather than scraping postings through a browser.

Capabilities grounded in real evidence:
:class:`~career_agent.agents.apply.form_fillers.LeverFormFiller` is this
project's other *fully verified* application-form filler (from a real,
live ``jobs.lever.co`` posting's DOM, ADR-0029/0035), confirming the
resume field (``[name='resume']``) is a **required file upload**
(``page.set_input_files``), with no manual-text alternative -- so
``supports_resume_upload=True`` here reflects verified reality. No
verified evidence exists for a separate cover-letter field or an "easy
apply" flow, so both stay ``False`` (unverified, not confirmed absent).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from career_agent.integrations.adapters.base import (
    AdapterCapabilities,
    BrowserAdapterMixin,
)
from career_agent.plugins.sources.lever import LeverSource

if TYPE_CHECKING:
    from career_agent.core.interfaces import HttpClient
    from career_agent.domain.models import Opportunity


class LeverAdapter(BrowserAdapterMixin):
    """Wraps :class:`LeverSource`; adds URL recognition + browser hooks."""

    provider = "lever"
    capabilities = AdapterCapabilities(
        supports_resume_upload=True,
        supports_cover_letter_upload=False,
        supports_easy_apply=False,
    )

    def __init__(self, companies: list[str], *, client: HttpClient) -> None:
        """Configure with the Lever company slugs to search.

        Also takes an HTTP client, injected for tests.
        """
        self._source = LeverSource(companies, client=client)

    def supports(self, url: str) -> bool:
        """Whether ``url`` is a Lever posting."""
        return "jobs.lever.co" in url.lower()

    async def search(self, *, since: datetime, **_: object) -> list[Opportunity]:
        """Delegates to :class:`LeverSource` -- see module docstring."""
        return await self._source.fetch(since)
