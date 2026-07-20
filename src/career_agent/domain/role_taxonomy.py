"""Curated tech-role taxonomy for search expansion (Phase 72, ADR-0090).

Pure data plus pure-Python matching, deliberately code-reviewed rather than
model-derived -- the same reasoning :mod:`career_agent.domain.
skills_taxonomy` already applies to keyword extraction: a search whose
"related roles" depend on a downloaded model artifact is only
deterministic *conditional on* that artifact's version being present. Same
input, same code version, same output, forever, on any machine.

A role family's ``synonyms`` are treated as interchangeable spellings of
the *same* role ("software developer" == "software engineer" == "SDE")
and only ever *widen* an exact-role match, never narrow it. A family's
``related`` set names *other*, adjacent families -- "software developer"
relates to "backend developer", "cloud engineer", and so on, because the
user's own broader role genuinely contains these as sub-roles. Related
terms are surfaced as a **separate bucket** (never merged into the exact
match), so a search stays precise while still surfacing adjacent roles a
candidate for the broader title would plausibly also want to see.

Extending this taxonomy is an ordinary, reviewed code change -- exactly
how :mod:`skills_taxonomy` is meant to evolve too. For a role title this
taxonomy has no entry for at all, :mod:`career_agent.domain.
role_expansion` falls back to an optional LLM port (Phase 72) -- but only
ever to *add* related-role suggestions, never to filter or exclude
anything a search would otherwise return.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Seniority: purely additive synonym expansion, never a filter. Searching
# "junior software developer" should also catch postings titled "entry
# level" or "associate" -- it must never hide a posting that omits a
# seniority word entirely (most postings do).
# ---------------------------------------------------------------------------

SENIORITY_SYNONYMS: dict[str, frozenset[str]] = {
    "junior": frozenset(
        {
            "junior", "jr", "entry level", "entry-level", "associate",
            "graduate", "new grad", "trainee", "level i", "l1", "i",
        }
    ),
    "mid": frozenset(
        {"mid level", "mid-level", "intermediate", "level ii", "l2", "ii"}
    ),
    "senior": frozenset(
        {"senior", "sr", "level iii", "l3", "iii", "staff", "principal", "lead"}
    ),
}


@dataclass(frozen=True)
class RoleFamily:
    """One canonical tech-role family: its own synonyms + adjacent families.

    ``related`` holds *canonical names* of other entries in
    :data:`ROLE_FAMILIES`, not raw synonym strings -- so a family's related
    set stays valid even if that other family's own synonym list grows.
    """

    canonical: str
    synonyms: frozenset[str]
    related: frozenset[str] = field(default_factory=frozenset)


ROLE_FAMILIES: dict[str, RoleFamily] = {
    family.canonical: family
    for family in (
        RoleFamily(
            canonical="software developer",
            synonyms=frozenset(
                {
                    "software developer", "software engineer", "developer",
                    "programmer", "swe", "sde", "software dev",
                    "application developer", "systems developer",
                }
            ),
            related=frozenset(
                {
                    "backend developer", "frontend developer",
                    "full-stack developer", "mobile developer",
                    "cloud engineer", "devops engineer", "data engineer",
                    "qa engineer", "site reliability engineer",
                }
            ),
        ),
        RoleFamily(
            canonical="backend developer",
            synonyms=frozenset(
                {
                    "backend developer", "backend engineer",
                    "back-end developer", "back end developer",
                    "api developer", "server-side developer",
                }
            ),
            related=frozenset(
                {
                    "software developer", "cloud engineer",
                    "devops engineer", "database engineer",
                }
            ),
        ),
        RoleFamily(
            canonical="frontend developer",
            synonyms=frozenset(
                {
                    "frontend developer", "frontend engineer",
                    "front-end developer", "front end developer",
                    "ui developer", "web developer", "javascript developer",
                }
            ),
            related=frozenset(
                {"software developer", "full-stack developer", "ux engineer"}
            ),
        ),
        RoleFamily(
            canonical="full-stack developer",
            synonyms=frozenset(
                {
                    "full-stack developer", "full stack developer",
                    "fullstack developer", "full-stack engineer",
                }
            ),
            related=frozenset(
                {"software developer", "backend developer", "frontend developer"}
            ),
        ),
        RoleFamily(
            canonical="mobile developer",
            synonyms=frozenset(
                {
                    "mobile developer", "mobile engineer", "ios developer",
                    "android developer", "app developer",
                }
            ),
            related=frozenset({"software developer", "frontend developer"}),
        ),
        RoleFamily(
            canonical="cloud engineer",
            synonyms=frozenset(
                {
                    "cloud engineer", "cloud developer", "cloud architect",
                    "aws engineer", "azure engineer", "gcp engineer",
                    "infrastructure engineer",
                }
            ),
            related=frozenset(
                {"devops engineer", "backend developer", "site reliability engineer"}
            ),
        ),
        RoleFamily(
            canonical="devops engineer",
            synonyms=frozenset(
                {"devops engineer", "devops", "platform engineer", "build engineer"}
            ),
            related=frozenset(
                {"cloud engineer", "site reliability engineer", "backend developer"}
            ),
        ),
        RoleFamily(
            canonical="site reliability engineer",
            synonyms=frozenset(
                {
                    "site reliability engineer", "sre",
                    "reliability engineer", "production engineer",
                }
            ),
            related=frozenset(
                {"devops engineer", "cloud engineer", "backend developer"}
            ),
        ),
        RoleFamily(
            canonical="data engineer",
            synonyms=frozenset(
                {
                    "data engineer", "big data engineer",
                    "etl developer", "data platform engineer",
                }
            ),
            related=frozenset(
                {"software developer", "data scientist", "machine learning engineer"}
            ),
        ),
        RoleFamily(
            canonical="data scientist",
            synonyms=frozenset({"data scientist", "data analyst", "applied scientist"}),
            related=frozenset({"data engineer", "machine learning engineer"}),
        ),
        RoleFamily(
            canonical="machine learning engineer",
            synonyms=frozenset(
                {
                    "machine learning engineer", "ml engineer",
                    "ai engineer", "deep learning engineer",
                }
            ),
            related=frozenset(
                {"data scientist", "data engineer", "software developer"}
            ),
        ),
        RoleFamily(
            canonical="qa engineer",
            synonyms=frozenset(
                {
                    "qa engineer", "quality assurance engineer",
                    "test engineer", "sdet", "qa analyst",
                    "software test engineer", "automation engineer",
                }
            ),
            related=frozenset({"software developer", "backend developer"}),
        ),
        RoleFamily(
            canonical="security engineer",
            synonyms=frozenset(
                {
                    "security engineer", "application security engineer",
                    "cybersecurity engineer", "infosec engineer",
                }
            ),
            related=frozenset(
                {"backend developer", "devops engineer", "cloud engineer"}
            ),
        ),
        RoleFamily(
            canonical="database engineer",
            synonyms=frozenset(
                {"database engineer", "dba", "database administrator"}
            ),
            related=frozenset({"backend developer", "data engineer"}),
        ),
        RoleFamily(
            canonical="ux engineer",
            synonyms=frozenset(
                {"ux engineer", "ux designer", "ui designer", "product designer"}
            ),
            related=frozenset({"frontend developer"}),
        ),
    )
}


@dataclass(frozen=True)
class RoleExpansion:
    """Everything the taxonomy could infer from one free-text role query.

    ``synonym_terms`` (including seniority variants) is the *exact-match*
    expansion of the query's own role -- a caller widens its existing exact
    match set with these. ``related_terms`` names *adjacent* roles and is
    always disjoint from ``synonym_terms``, meant for a clearly separate
    "related roles" bucket, never silently merged into exact results.
    """

    matched_families: frozenset[str] = frozenset()
    synonym_terms: frozenset[str] = frozenset()
    related_terms: frozenset[str] = frozenset()
    related_family_names: frozenset[str] = frozenset()

    @property
    def is_known(self) -> bool:
        """False when nothing in the curated taxonomy recognized this query."""
        return bool(self.matched_families)


def _phrase_present(phrase: str, text: str) -> bool:
    """Whole-word/whole-phrase containment, case-insensitive.

    Word-boundary matched (not naive substring) so a short synonym like
    "qa" or "sre" cannot accidentally match inside an unrelated word.
    """
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


def expand_role(query: str) -> RoleExpansion:
    """Expand a free-text role query using the curated taxonomy alone.

    Pure and deterministic -- no I/O, no model calls. Returns an empty,
    ``is_known=False`` expansion for a query that matches no known family
    (the caller's own literal terms remain the only match set; see
    :mod:`career_agent.domain.role_expansion` for the optional LLM
    fallback used only in that case).
    """
    normalized = re.sub(r"\s+", " ", query.strip().lower())
    if not normalized:
        return RoleExpansion()

    matched_families = {
        family.canonical
        for family in ROLE_FAMILIES.values()
        if any(_phrase_present(syn, normalized) for syn in family.synonyms)
    }
    if not matched_families:
        return RoleExpansion()

    synonym_terms: set[str] = set()
    related_family_names: set[str] = set()
    for name in matched_families:
        family = ROLE_FAMILIES[name]
        synonym_terms |= family.synonyms
        related_family_names |= family.related
    related_family_names -= matched_families

    related_terms: set[str] = set()
    for name in related_family_names:
        related_terms |= ROLE_FAMILIES[name].synonyms
    related_terms -= synonym_terms

    for level_terms in SENIORITY_SYNONYMS.values():
        if any(_phrase_present(term, normalized) for term in level_terms):
            synonym_terms |= level_terms

    return RoleExpansion(
        matched_families=frozenset(matched_families),
        synonym_terms=frozenset(synonym_terms),
        related_terms=frozenset(related_terms),
        related_family_names=frozenset(related_family_names),
    )
