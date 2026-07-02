"""The load-bearing test for 4c slice-3: eligibility excludes, it doesn't just
score lower, and an all-ineligible query raises rather than silently returning
something wrong.
"""

from __future__ import annotations

import pytest

from career_agent.core.interfaces import (
    ProviderCapabilities,
    ProviderHealth,
    SearchQuery,
    SearchResult,
)
from career_agent.core.ranking import (
    NoEligibleProviderError,
    is_eligible,
    score_provider,
    select_provider,
)


class _FakeProvider:
    """A minimal SearchProvider stand-in with fixed capabilities/health."""

    def __init__(
        self, name: str, capabilities: ProviderCapabilities, health: ProviderHealth
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        self._health = health

    async def health(self) -> ProviderHealth:
        return self._health

    async def search(  # pragma: no cover
        self, query: SearchQuery
    ) -> list[SearchResult]:
        return []


_SEMANTIC = ProviderCapabilities(
    supports_site_search=True,
    supports_freshness=True,
    supports_news=False,
    supports_semantic_search=True,
    supports_images=False,
)
_KEYWORD_ONLY = ProviderCapabilities(
    supports_site_search=True,
    supports_freshness=True,
    supports_news=False,
    supports_semantic_search=False,
    supports_images=False,
)
_HEALTHY = ProviderHealth(
    latency_ms_p50=100.0, success_rate=1.0, cost_per_query=0.005
)
_UNHEALTHY = ProviderHealth(
    latency_ms_p50=100.0, success_rate=0.2, cost_per_query=0.005
)


def test_semantic_query_excludes_keyword_only_provider_entirely() -> None:
    """The eligibility gate: a semantic query must never even CONSIDER a
    non-semantic provider, not merely score it lower."""
    assert is_eligible(_SEMANTIC, SearchQuery(text="x", requires_semantic=True)) is True
    assert (
        is_eligible(_KEYWORD_ONLY, SearchQuery(text="x", requires_semantic=True))
        is False
    )


def test_keyword_query_considers_both_capability_shapes() -> None:
    query = SearchQuery(text="x")  # no semantic requirement
    assert is_eligible(_SEMANTIC, query) is True
    assert is_eligible(_KEYWORD_ONLY, query) is True


async def test_select_provider_excludes_ineligible_even_if_higher_scoring() -> None:
    """The eligibility gate is checked BEFORE scoring: a keyword-only provider
    with perfect health must still be excluded from a semantic query, even
    though its health score would beat an unhealthy-but-eligible provider."""
    exa_like = _FakeProvider("exa", _SEMANTIC, _UNHEALTHY)
    # better health, but the wrong capability -- must still be excluded
    cse_like = _FakeProvider("cse", _KEYWORD_ONLY, _HEALTHY)
    chosen = await select_provider(
        [exa_like, cse_like], SearchQuery(text="x", requires_semantic=True)
    )
    assert chosen is exa_like  # the only eligible one, despite worse health


async def test_select_provider_picks_the_healthier_eligible_provider() -> None:
    good = _FakeProvider("good", _SEMANTIC, _HEALTHY)
    bad = _FakeProvider("bad", _SEMANTIC, _UNHEALTHY)
    chosen = await select_provider([bad, good], SearchQuery(text="x"))
    assert chosen is good


async def test_all_ineligible_raises_not_none_not_a_bad_provider() -> None:
    """The other behavioral guarantee: no registered provider satisfying the
    query must raise, not silently return an ineligible provider or None that
    could be swallowed upstream."""
    cse_like = _FakeProvider("cse", _KEYWORD_ONLY, _HEALTHY)
    with pytest.raises(NoEligibleProviderError):
        await select_provider(
            [cse_like], SearchQuery(text="x", requires_semantic=True)
        )


async def test_empty_provider_list_raises() -> None:
    with pytest.raises(NoEligibleProviderError):
        await select_provider([], SearchQuery(text="x"))


def test_score_favors_success_over_latency_and_cost() -> None:
    reliable_slow = ProviderHealth(
        latency_ms_p50=300.0, success_rate=1.0, cost_per_query=0.01
    )
    unreliable_fast = ProviderHealth(
        latency_ms_p50=10.0, success_rate=0.5, cost_per_query=0.001
    )
    assert score_provider(reliable_slow) > score_provider(unreliable_fast)
