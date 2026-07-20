"""Role-relevance filtering for discovered opportunities (Phase 70, Phase 72).

Some opportunity sources (Adzuna/Reed/USAJobs/Jooble) filter by keyword
server-side; the free firehose sources (RemoteOK/Remotive/Arbeitnow/
TheMuse) return *every* recent remote posting regardless of role. Without
a client-side relevance gate, a search for "software engineer" surfaces
baristas and nannies -- the sources that ignore the query drown out the
ones that honor it.

This started (Phase 70) as a purely literal bag-of-words matcher over the
user's configured ``preferred_titles``/``alternative_titles``; that part
(:func:`role_terms`/:func:`opportunity_matches_role`) is unchanged.

Phase 72 (ADR-0090) adds taxonomy-aware classification via
:func:`relevance_tier`, deliberately kept **separate** from the literal
token bag rather than merged into it: an early implementation tokenized
taxonomy synonyms into the same flat set and immediately produced two
false results in testing --

- "Data Entry Typist" matched a "Software Developer" search as related,
  because "data" alone (from the unrelated "data engineer"/"data
  scientist" families) is a shared *token*, even though neither title
  shares a real *phrase*.
- "Backend Developer" matched a "Software Developer" search as *exact*
  (not the intended "related"), because the single generic word
  "developer" is shared between the two families' names, even though
  "backend developer" is unambiguously the more specific, adjacent role.

Both are the same root cause: single generic words ("data", "developer",
"engineer") are exactly what makes two *different* role families
nameable in the first place, so decomposing a multi-word family name into
a token bag destroys the distinction the taxonomy exists to draw.
:func:`relevance_tier` therefore matches taxonomy synonyms as **whole
phrases** (word-boundary, not token-set overlap) against the opportunity
title, and checks the more specific ``related`` families *before* the
caller's own ``exact`` family -- so a title that names a more specific
adjacent role is never absorbed into the coarser exact match just because
they share one generic word.
"""

from __future__ import annotations

import re
from typing import Literal

from career_agent.domain.job_preferences import JobPreferences
from career_agent.domain.models import Opportunity
from career_agent.domain.role_taxonomy import ROLE_FAMILIES, expand_role

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


def _phrase_present(phrase: str, text: str) -> bool:
    """Whole-word/whole-phrase containment, case-insensitive."""
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


def role_terms(preferences: JobPreferences) -> set[str]:
    """The set of discriminating role tokens the user literally configured.

    Unchanged from Phase 70 -- purely the caller's own words, tokenized.
    Taxonomy-based widening lives entirely in :func:`relevance_tier`
    instead of here (see this module's docstring for why merging it into
    this flat token set produces false matches).
    """
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
    """
    if not terms:
        return True
    return bool(_tokens(opportunity.title) & terms)


def _configured_families(
    preferences: JobPreferences,
) -> tuple[set[str], set[str]]:
    """(matched family names, related family names) across every configured title.

    Related names exclude anything also matched directly, and neither set
    includes titles the taxonomy has no entry for at all (those contribute
    nothing here -- only to the literal token bag ``role_terms`` already
    covers).
    """
    matched: set[str] = set()
    related: set[str] = set()
    for title in (*preferences.preferred_titles, *preferences.alternative_titles):
        expansion = expand_role(title)
        matched |= expansion.matched_families
        related |= expansion.related_family_names
    related -= matched
    return matched, related


def _title_matches_any_family(title: str, family_names: set[str]) -> bool:
    """Whole-phrase match of the title against every synonym of each family.

    Never a token-bag comparison -- see this module's docstring for why.
    """
    normalized = title.lower()
    return any(
        _phrase_present(synonym, normalized)
        for name in family_names
        for synonym in ROLE_FAMILIES[name].synonyms
    )


def relevance_tier(
    opportunity: Opportunity,
    preferences: JobPreferences,
    *,
    extra_related_terms: frozenset[str] = frozenset(),
) -> Literal["exact", "related", "none"]:
    """Classify ``opportunity`` against the caller's configured role search.

    ``"exact"`` -- matches a configured title's own literal tokens (Phase
    70) or, via the curated taxonomy, one of that title's own role-family
    synonym phrases. ``"related"`` -- matches none of those, but does match
    an *adjacent* sub-role family the taxonomy names for a configured title
    (e.g. a "Backend Developer" posting for a "Software Developer" search),
    or one of ``extra_related_terms``. ``"none"`` -- matches neither, or
    the company is blacklisted. No role configured at all means everything
    is ``"exact"`` (Phase 70's "matches everything" behavior, unchanged).

    ``extra_related_terms`` (Phase 72, ADR-0090) is the caller's own
    pre-computed widening of the ``related`` tier -- typically
    :func:`~career_agent.domain.role_expansion.
    suggest_related_terms_for_unknown_role`'s output for a role the
    taxonomy has no entry for at all. Plain bag-of-words tokens (unlike
    the taxonomy's phrase matching), matched the same way
    :func:`role_terms` already is -- these terms are free-text LLM
    suggestions, not canonical family names, so there is no family
    synonym list to phrase-match against. Always additive: it can only
    ever turn a ``"none"`` into a ``"related"``, never an ``"exact"``.

    Related families are checked *before* the exact literal/taxonomy match
    on purpose: a title naming a more specific adjacent role (e.g. "Backend
    Developer") must classify as ``"related"`` even though it shares a
    generic word ("developer") with the broader exact family -- see this
    module's docstring for the false-positive this ordering fixes.
    """
    blacklisted = {name.strip().lower() for name in preferences.blacklisted_companies}
    if opportunity.canonical_company.strip().lower() in blacklisted:
        return "none"

    literal_terms = role_terms(preferences)
    if not literal_terms:
        return "exact"

    matched_families, related_families = _configured_families(preferences)

    if related_families and _title_matches_any_family(
        opportunity.title, related_families
    ):
        return "related"
    if opportunity_matches_role(opportunity, literal_terms):
        return "exact"
    if matched_families and _title_matches_any_family(
        opportunity.title, matched_families
    ):
        return "exact"
    if extra_related_terms and (_tokens(opportunity.title) & extra_related_terms):
        return "related"
    return "none"


def matches_search(
    opportunity: Opportunity, preferences: JobPreferences
) -> bool:
    """Whether a discovered ``opportunity`` belongs in the caller's results.

    True for both the ``"exact"`` and ``"related"`` tiers (Phase 72) -- an
    adjacent-role posting is still worth surfacing, never silently dropped;
    see :func:`relevance_tier` for the finer-grained classification a
    caller can use to label "related" results separately.
    """
    return relevance_tier(opportunity, preferences) != "none"
