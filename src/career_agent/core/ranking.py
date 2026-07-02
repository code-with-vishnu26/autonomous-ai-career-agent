"""Search-provider ranking (ADR-0002; 4c slice-3, an ADR-0002 amendment).

Two pure functions over ``(capabilities, health, query)`` -- no dependency on
the Planner, the plugin registry's internals beyond ``all()``, or any
persistence beyond what a provider's own ``health()`` already returns. What
calls :func:`select_provider`, when, and how failures are retried are Planner
concerns and are explicitly out of scope here (see the ADR-0002 amendment).
"""

from __future__ import annotations

from career_agent.core.interfaces import (
    ProviderCapabilities,
    ProviderHealth,
    SearchProvider,
    SearchQuery,
)

# Weights are relative, not normalized to any particular scale; only their
# ratios matter since scores are compared, never displayed as an absolute
# quality percentage.
_SUCCESS_WEIGHT = 10.0
_LATENCY_WEIGHT = 1.0
_COST_WEIGHT = 5.0


class NoEligibleProviderError(Exception):
    """Raised when no registered provider can satisfy a query's requirements.

    Deliberately raised rather than silently falling back to an ineligible
    provider: a semantic query answered by a keyword-only provider would be a
    degraded result presented as if it were a considered choice -- the
    discovery-side equivalent of emitting an unverified result as confident.
    Same fail-loud instinct as duplicate plugin registration (ADR-0004).
    """


def is_eligible(capabilities: ProviderCapabilities, query: SearchQuery) -> bool:
    """Return whether a provider's capabilities satisfy ``query``'s requirements.

    A query's requirements are a floor, not a preference: a provider missing a
    required capability is not merely scored lower, it is excluded entirely.
    """
    if query.requires_semantic and not capabilities.supports_semantic_search:
        return False
    if query.requires_freshness and not capabilities.supports_freshness:
        return False
    if query.site and not capabilities.supports_site_search:
        return False
    return True


def score_provider(health: ProviderHealth) -> float:
    """Score an eligible provider's health: higher is better.

    Favors high success rate, low latency, and low cost. Only called for
    providers that already passed :func:`is_eligible` -- capability fitness is
    a gate, not a scoring term, so an eligible-but-slower provider can still
    outrank a technically-eligible-but-flaky one on the same query.
    """
    return (
        _SUCCESS_WEIGHT * health.success_rate
        - _LATENCY_WEIGHT * (health.latency_ms_p50 / 1000.0)
        - _COST_WEIGHT * health.cost_per_query
    )


async def select_provider(
    providers: list[SearchProvider], query: SearchQuery
) -> SearchProvider:
    """Return the best eligible provider for ``query`` from ``providers``.

    Raises :class:`NoEligibleProviderError` if none of ``providers`` satisfies
    ``query``'s capability requirements -- never silently returns an
    ineligible provider.
    """
    eligible = [p for p in providers if is_eligible(p.capabilities, query)]
    if not eligible:
        raise NoEligibleProviderError(
            f"no registered provider satisfies query requirements "
            f"(semantic={query.requires_semantic}, "
            f"freshness={query.requires_freshness}, site={query.site!r})"
        )
    scored = [(await p.health(), p) for p in eligible]
    return max(scored, key=lambda pair: score_provider(pair[0]))[1]
