"""Tests for the Google CSE SearchProvider (fixture-driven, offline, no live key)."""

from __future__ import annotations

from career_agent.core.interfaces import SearchProvider, SearchQuery
from career_agent.plugins.search.google_cse import GoogleCSESearchProvider
from tests._fakes import FakeHttpClient, load_fixture


def _provider() -> tuple[GoogleCSESearchProvider, FakeHttpClient]:
    client = FakeHttpClient(
        {"customsearch/v1": load_fixture("google_cse", "search_results.json")}
    )
    provider = GoogleCSESearchProvider(
        api_key="fake-key-never-a-real-one", cse_id="fake-cse-id", client=client
    )
    return provider, client


def test_google_cse_satisfies_the_search_provider_protocol() -> None:
    provider, _ = _provider()
    assert isinstance(provider, SearchProvider)


def test_google_cse_is_keyword_only_not_semantic() -> None:
    """The reason CSE was built second: it's the keyword-only contrast to
    Exa's semantic search -- this is the capability difference the ranking
    module's eligibility gate is built to distinguish."""
    provider, _ = _provider()
    assert provider.capabilities.supports_semantic_search is False


async def test_search_uses_get_with_params_not_post() -> None:
    """Google CSE's real API is GET+params; confirms no post_json call is made
    (unlike Exa)."""
    provider, client = _provider()
    await provider.search(SearchQuery(text="acme backend engineer"))
    assert client.post_calls == []
    assert len(client.calls) == 1
    url, params = client.calls[0]
    assert url.endswith("customsearch/v1")
    assert params["q"] == "acme backend engineer"
    assert params["key"] == "fake-key-never-a-real-one"


async def test_search_returns_normalized_results() -> None:
    provider, _ = _provider()
    results = await provider.search(SearchQuery(text="acme backend engineer"))
    assert len(results) == 2
    assert results[0].url == "https://boards.greenhouse.io/acme/jobs/4012345"


async def test_health_reports_success_after_a_call() -> None:
    provider, _ = _provider()
    await provider.search(SearchQuery(text="x"))
    health = await provider.health()
    assert health.success_rate == 1.0
