"""Google Custom Search Engine :class:`SearchProvider` (4c slice-3).

The second, keyword-shaped provider. Built after Exa specifically so the
capability-ranking machinery (see :mod:`career_agent.core.ranking`) has a real
difference to distinguish: Google CSE is keyword-only
(``supports_semantic_search=False``), the direct contrast to Exa's semantic
search. A semantic query is ineligible for this provider by construction, not
by a lower score -- see the ranking module's eligibility gate.

The real API (``GET customsearch/v1?key=...&cx=...&q=...``) is genuinely
GET-shaped, so this provider needs no ``post_json``.

Config-bearing (an API key + a search-engine id + an HTTP client), registered
explicitly by the composition root, same isolation as Exa: this module never
imports ``career_agent.core.config`` (enforced by the same import-linter
contract).
"""

from __future__ import annotations

import time

from career_agent.core.interfaces import (
    HttpClient,
    ProviderCapabilities,
    ProviderHealth,
    SearchQuery,
    SearchResult,
)

_DEFAULT_BASE_URL = "https://www.googleapis.com/customsearch/v1"


class GoogleCSESearchProvider:
    """Google Custom Search Engine-backed :class:`SearchProvider`."""

    capabilities = ProviderCapabilities(
        supports_site_search=True,  # native `siteSearch` param
        supports_freshness=True,  # native `dateRestrict` param
        supports_news=False,
        supports_semantic_search=False,  # keyword-only: the contrast to Exa
        supports_images=False,
    )

    def __init__(
        self,
        *,
        api_key: str,
        cse_id: str,
        client: HttpClient,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        """Configure the provider with a bare API key, engine id, and client.

        Both ``api_key`` and ``cse_id`` are plain strings, not a
        :class:`~career_agent.core.config.Settings` object -- same isolation
        pattern as :class:`~career_agent.plugins.search.exa.ExaSearchProvider`.
        """
        self._api_key = api_key
        self._cse_id = cse_id
        self._client = client
        self._base_url = base_url
        self._latencies_ms: list[float] = []
        self._successes = 0
        self._failures = 0

    async def health(self) -> ProviderHealth:
        """Return rolling health stats from calls made so far."""
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
        """Run ``query`` against Google CSE and return normalized results."""
        params = {"key": self._api_key, "cx": self._cse_id, "q": query.text}
        if query.site:
            params["siteSearch"] = query.site
        if query.requires_freshness:
            params["dateRestrict"] = "y1"  # past year

        started = time.monotonic()
        try:
            payload = await self._client.get_json(self._base_url, params=params)
        except Exception:
            self._failures += 1
            raise
        self._latencies_ms.append((time.monotonic() - started) * 1000)
        self._successes += 1
        return _results_of(payload)


def _results_of(payload: object) -> list[SearchResult]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    out: list[SearchResult] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        link = raw.get("link")
        if not isinstance(link, str) or not link:
            continue
        title = raw.get("title")
        snippet = raw.get("snippet")
        out.append(
            SearchResult(
                url=link,
                title=title if isinstance(title, str) else "",
                snippet=snippet if isinstance(snippet, str) else "",
            )
        )
    return out
