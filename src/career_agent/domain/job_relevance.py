"""Role-relevance filtering for discovered opportunities (Phase 70).

Some opportunity sources (Adzuna/Reed/USAJobs/Jooble) filter by keyword
server-side; the free firehose sources (RemoteOK/Remotive/Arbeitnow/
TheMuse) return *every* recent remote posting regardless of role. Without
a client-side relevance gate, a search for "software engineer" surfaces
baristas and nannies -- the sources that ignore the query drown out the
ones that honor it.

This module is a pure, deterministic keyword matcher over the role titles
the user configured (``preferred_titles`` + ``alternative_titles``). It is
deliberately literal -- it matches the user's own words, not a synonym
model -- so the result is predictable: if you want "developer" roles too,
add "developer" as an alternative title. When no role titles are
configured it matches everything, so discovery's prior behavior is
unchanged for a user who never set a role.
"""

from __future__ import annotations

import re

from career_agent.domain.job_preferences import JobPreferences
from career_agent.domain.models import Opportunity

#: Tokens too generic to discriminate a role -- dropped from the match set
#: so "software engineer" keys on {software, engineer}, not {a, of, ...}.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "or", "the", "of", "for", "to", "in", "at", "on",
        "with", "job", "jobs", "role", "roles", "position", "positions",
        "remote", "hybrid", "onsite", "full", "part", "time",
    }
)
_MIN_TOKEN_LEN = 3


def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric word tokens, minus stopwords and tiny words."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORDS
    }


def role_terms(preferences: JobPreferences) -> set[str]:
    """The set of discriminating role tokens the user configured."""
    terms: set[str] = set()
    for title in (*preferences.preferred_titles, *preferences.alternative_titles):
        terms |= _tokens(title)
    return terms


def opportunity_matches_role(
    opportunity: Opportunity, terms: set[str]
) -> bool:
    """True if the opportunity's title shares any configured role token.

    Empty ``terms`` (no role configured) matches everything -- discovery
    is only *narrowed* by a real role filter, never blocked by its absence.
    Blacklisted companies are always excluded regardless of title match.
    """
    if not terms:
        return True
    return bool(_tokens(opportunity.title) & terms)


def matches_search(
    opportunity: Opportunity, preferences: JobPreferences
) -> bool:
    """Whether a discovered ``opportunity`` matches the caller's search.

    Combines the role-title token match with the blacklisted-company
    exclusion. A convenience wrapper over :func:`role_terms` +
    :func:`opportunity_matches_role` for callers that hold the full
    preferences (recomputing ``role_terms`` per call is cheap and keeps
    the call site a one-liner).
    """
    blacklisted = {name.strip().lower() for name in preferences.blacklisted_companies}
    if opportunity.canonical_company.strip().lower() in blacklisted:
        return False
    return opportunity_matches_role(opportunity, role_terms(preferences))
