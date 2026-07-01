"""A trivial example :class:`SearchProvider` demonstrating plugin registration.

``EchoSearchProvider`` implements the ADR-0002 search-provider contract and is
registered under ``(SearchProvider, "echo")`` via the :func:`register`
decorator. It performs no network I/O -- it simply echoes the query back as a
single result -- so it can prove the register-and-discover flow end to end in
tests without any external dependency.
"""

from __future__ import annotations

from career_agent.core.interfaces import (
    ProviderCapabilities,
    ProviderHealth,
    SearchProvider,
    SearchQuery,
    SearchResult,
)
from career_agent.core.registry import register


@register(SearchProvider, "echo")
class EchoSearchProvider:
    """An example provider that echoes the query text back as one result."""

    capabilities = ProviderCapabilities(
        supports_site_search=False,
        supports_freshness=False,
        supports_news=False,
        supports_semantic_search=False,
        supports_images=False,
    )

    async def health(self) -> ProviderHealth:
        """Report perfect, free, instant health -- it does no real work."""
        return ProviderHealth(
            latency_ms_p50=0.0, success_rate=1.0, cost_per_query=0.0
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return a single result echoing ``query.text``."""
        return [
            SearchResult(
                url="https://example.invalid/echo",
                title=f"echo: {query.text}",
                snippet=query.text,
            )
        ]
