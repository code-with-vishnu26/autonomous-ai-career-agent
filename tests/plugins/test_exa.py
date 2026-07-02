"""Tests for the Exa SearchProvider (fixture-driven, offline, no live key)."""

from __future__ import annotations

from career_agent.core.interfaces import SearchProvider, SearchQuery
from career_agent.plugins.search.exa import ExaSearchProvider
from tests._fakes import FakeHttpClient, load_fixture


def _provider() -> tuple[ExaSearchProvider, FakeHttpClient]:
    client = FakeHttpClient({"/search": load_fixture("exa", "search_results.json")})
    return ExaSearchProvider(api_key="fake-key-never-a-real-one", client=client), client


def test_exa_satisfies_the_search_provider_protocol() -> None:
    provider, _ = _provider()
    assert isinstance(provider, SearchProvider)


def test_exa_declares_semantic_search_capability() -> None:
    """The reason Exa was built first: it's the provider that exercises
    supports_semantic_search, which slice-3's ranking is built to distinguish
    providers on."""
    provider, _ = _provider()
    assert provider.capabilities.supports_semantic_search is True


async def test_search_uses_post_not_get() -> None:
    """Exa's real API is POST+JSON body; confirms the client is called via
    post_json, not get_json (the reason HttpClient gained post_json)."""
    provider, client = _provider()
    await provider.search(SearchQuery(text="senior backend engineer remote"))
    assert client.calls == []  # get_json never called
    assert len(client.post_calls) == 1
    url, body = client.post_calls[0]
    assert url.endswith("/search")
    assert body["query"] == "senior backend engineer remote"


async def test_search_returns_normalized_results() -> None:
    provider, _ = _provider()
    results = await provider.search(SearchQuery(text="acme backend engineer"))
    assert len(results) == 3
    assert results[0].url == "https://boards.greenhouse.io/acme/jobs/4012345"
    assert results[0].title == "Senior Backend Engineer at Acme"


async def test_health_reports_success_after_a_call() -> None:
    provider, _ = _provider()
    await provider.search(SearchQuery(text="x"))
    health = await provider.health()
    assert health.success_rate == 1.0
    assert health.latency_ms_p50 >= 0.0


async def test_health_before_any_call_is_optimistic_default() -> None:
    provider, _ = _provider()
    health = await provider.health()
    assert health.success_rate == 1.0
    assert health.latency_ms_p50 == 0.0
