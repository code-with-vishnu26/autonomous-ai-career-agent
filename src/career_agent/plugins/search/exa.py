"""Exa :class:`SearchProvider` (ADR-0002, 4c slice-2).

Exa is semantically-native search, which is why it is the first provider
built: it fits this system's quality-over-volume goal (semantic relevance of a
query like "senior backend roles at early-stage startups doing X") better than
keyword search, and it is the provider that actually exercises
``supports_semantic_search`` -- the capability slice-3's dynamic ranking is
built to distinguish between providers on.

The Exa search API is POST with a JSON body, not GET with query params, hence
:meth:`~career_agent.core.interfaces.HttpClient.post_json` (added in this
slice, additively).

Config-bearing (an API key + an HTTP client), so registered explicitly by the
composition root -- which reads :class:`~career_agent.core.config.Settings`
and hands this provider its key. This module never imports
``career_agent.core.config`` itself (enforced by an import-linter contract):
config flows inward by injection, not outward by import.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from career_agent.core.interfaces import (
    HttpClient,
    ProviderCapabilities,
    ProviderHealth,
    SearchQuery,
    SearchResult,
)

_DEFAULT_BASE_URL = "https://api.exa.ai"


class ExaSearchProvider:
    """Exa-backed :class:`SearchProvider`."""

    capabilities = ProviderCapabilities(
        supports_site_search=True,
        supports_freshness=True,
        supports_news=False,
        supports_semantic_search=True,
        supports_images=False,
    )

    def __init__(
        self,
        *,
        api_key: str,
        client: HttpClient,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        """Configure the provider with a bare API key and an HTTP client.

        ``api_key`` is a plain string, not a :class:`~career_agent.core.config.
        Settings` object -- this constructor is where config stops flowing
        inward and becomes a concrete value, so this class stays constructible
        and testable in isolation with a fake key and no config dependency.
        """
        self._api_key = api_key
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._latencies_ms: list[float] = []
        self._successes = 0
        self._failures = 0

    async def health(self) -> ProviderHealth:
        """Return rolling health stats from calls made so far.

        Cost is a static per-query estimate (Exa's published rate), not yet
        wired to real billing; latency/success are genuinely rolling.
        """
        count = self._successes + self._failures
        success_rate = self._successes / count if count else 1.0
        latency = (
            sum(self._latencies_ms) / len(self._latencies_ms)
            if self._latencies_ms
            else 0.0
        )
        return ProviderHealth(
            latency_ms_p50=latency, success_rate=success_rate, cost_per_query=0.005
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Run ``query`` against Exa and return normalized results."""
        body: dict[str, object] = {
            "query": query.text,
            "type": "neural" if query.requires_semantic else "keyword",
            "numResults": 10,
            "contents": {"text": {"maxCharacters": 500}},
        }
        if query.requires_freshness:
            body["startPublishedDate"] = _one_year_ago()
        if query.site:
            body["includeDomains"] = [query.site]

        started = time.monotonic()
        try:
            payload = await self._client.post_json(
                f"{self._base_url}/search",
                json=body,
                headers={"x-api-key": self._api_key},
            )
        except Exception:
            self._failures += 1
            raise
        self._latencies_ms.append((time.monotonic() - started) * 1000)
        self._successes += 1
        return _results_of(payload)


def _results_of(payload: object) -> list[SearchResult]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    out: list[SearchResult] = []
    for raw in results:
        if not isinstance(raw, dict):
            continue
        url = raw.get("url")
        if not isinstance(url, str) or not url:
            continue
        title = raw.get("title")
        text = raw.get("text")
        out.append(
            SearchResult(
                url=url,
                title=title if isinstance(title, str) else "",
                snippet=text if isinstance(text, str) else "",
            )
        )
    return out


def _one_year_ago() -> str:
    return (datetime.now(UTC) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
