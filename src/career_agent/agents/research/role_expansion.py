"""Combine the curated role taxonomy with an optional LLM fallback (Phase 72, ADR-0090).

:func:`~career_agent.domain.role_taxonomy.expand_role` is the primary,
deterministic, free mechanism -- it covers this project's own domain
(common tech roles) with zero I/O and zero cost. This module adds exactly
one thing on top: when a role query matches *nothing* in the curated
taxonomy, and an optional :class:`~career_agent.core.interfaces.
RoleExpander` LLM port is available, ask it for related role titles.

The LLM's suggestions become **only** extra ``related``-tier search terms
(see :func:`~career_agent.domain.job_relevance.relevance_tier`) -- they can
never widen an ``exact`` match and never gate or filter anything a search
would otherwise return, the same "advisory only" contract
``SemanticKeywordMatcher`` already follows for the ATS gate (ADR-0034). A
taxonomy hit never calls the LLM at all (the common case, fully
deterministic); a missing/failed/unconfigured port degrades to an empty
suggestion set, never an exception into a search request.
"""

from __future__ import annotations

from career_agent.core.interfaces import RoleExpander
from career_agent.domain.role_taxonomy import expand_role


async def suggest_related_terms_for_unknown_role(
    query: str, expander: RoleExpander | None
) -> frozenset[str]:
    """Related-role term suggestions for a query the taxonomy doesn't know.

    Returns an empty set immediately -- without ever calling ``expander``
    -- when the curated taxonomy already recognizes ``query`` (it already
    has its own, better, free related-role terms) or when ``expander`` is
    ``None`` (no LLM key configured). Any exception from the port itself
    (network error, malformed response) is swallowed the same way: an
    empty set, never a broken search.
    """
    if expand_role(query).is_known or expander is None:
        return frozenset()
    try:
        suggestions = await expander.suggest_related_roles(query)
    except Exception:  # noqa: BLE001 -- best-effort; a search must never break
        return frozenset()
    return frozenset(s.strip().lower() for s in suggestions if s and s.strip())
