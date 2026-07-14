"""Phase 70/72: role-relevance filtering for discovered opportunities."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.domain.job_preferences import JobPreferences
from career_agent.domain.job_relevance import (
    matches_search,
    relevance_tier,
    role_terms,
)
from career_agent.domain.models import Opportunity, Provenance


def _opp(title: str, company: str = "acme") -> Opportunity:
    return Opportunity(
        id="1",
        company_id="acme",
        canonical_company=company,
        title=title,
        source="job_board",
        source_url="https://example.invalid/1",
        provenance=Provenance(
            method="text_extraction", reference="r", extraction_confidence=1.0
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_role_terms_tokenizes_titles_dropping_stopwords() -> None:
    # role_terms() stays the caller's own literal words only -- taxonomy
    # widening lives entirely in relevance_tier (Phase 72), never merged
    # into this flat token set (see job_relevance.py's module docstring
    # for the false-positive that merging it in caused).
    prefs = JobPreferences(preferred_titles=["Software Engineer"])
    assert role_terms(prefs) == {"software", "engineer"}


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer",
        "Backend Engineer",
        "Full Stack Engineer @ octaleads",
        "Senior Software Developer",  # matches on "software"
    ],
)
def test_matching_roles_pass(title: str) -> None:
    prefs = JobPreferences(preferred_titles=["Software Engineer"])
    assert matches_search(_opp(title), prefs) is True


@pytest.mark.parametrize(
    "title",
    ["Data Entry Typist", "Barista", "Nanny", "Firefighter ARFF", "Mason"],
)
def test_off_role_titles_are_excluded(title: str) -> None:
    prefs = JobPreferences(preferred_titles=["Software Engineer"])
    assert matches_search(_opp(title), prefs) is False


def test_no_configured_role_matches_everything() -> None:
    # Discovery is only narrowed by a real role filter, never blocked by its
    # absence -- a user who never set a role still sees results.
    assert matches_search(_opp("Barista"), JobPreferences()) is True


def test_alternative_titles_widen_the_match() -> None:
    prefs = JobPreferences(
        preferred_titles=["Software Engineer"], alternative_titles=["Data Analyst"]
    )
    assert matches_search(_opp("Senior Data Analyst"), prefs) is True


def test_blacklisted_company_is_excluded_even_on_title_match() -> None:
    prefs = JobPreferences(
        preferred_titles=["Software Engineer"], blacklisted_companies=["Evil Corp"]
    )
    opp = _opp("Software Engineer", company="Evil Corp")
    assert matches_search(opp, prefs) is False


# --- Phase 72: taxonomy-aware exact/related tier classification ----------


def test_junior_software_developer_still_matches_junior_engineer_postings() -> None:
    prefs = JobPreferences(preferred_titles=["Junior Software Developer"])
    assert relevance_tier(_opp("Junior Software Engineer"), prefs) == "exact"
    assert relevance_tier(_opp("Entry Level Software Engineer"), prefs) == "exact"


def test_related_role_tier_surfaces_adjacent_roles_not_the_exact_search() -> None:
    prefs = JobPreferences(preferred_titles=["Software Developer"])
    assert relevance_tier(_opp("Backend Developer"), prefs) == "related"
    assert relevance_tier(_opp("Cloud Engineer"), prefs) == "related"
    assert relevance_tier(_opp("DevOps Engineer"), prefs) == "related"


def test_related_role_tier_is_still_a_match_via_matches_search() -> None:
    prefs = JobPreferences(preferred_titles=["Software Developer"])
    assert matches_search(_opp("Backend Developer"), prefs) is True


def test_unrelated_posting_is_neither_exact_nor_related() -> None:
    prefs = JobPreferences(preferred_titles=["Software Developer"])
    assert relevance_tier(_opp("Barista"), prefs) == "none"
    assert matches_search(_opp("Barista"), prefs) is False


def test_ambiguous_single_word_overlap_does_not_create_a_false_related_match() -> None:
    # Regression: "data" alone (shared with the unrelated "data engineer"/
    # "data scientist" families) must not classify "Data Entry Typist" as
    # related to a "Software Developer" search -- phrase matching, not
    # token-bag overlap, is what prevents this.
    prefs = JobPreferences(preferred_titles=["Software Developer"])
    assert relevance_tier(_opp("Data Entry Typist"), prefs) == "none"


def test_more_specific_related_role_is_not_absorbed_into_exact_match() -> None:
    # Regression: "developer" alone is shared between "Software Developer"
    # and "Backend Developer" -- the more specific adjacent role must win,
    # not fall into "exact" just because of the shared generic word.
    prefs = JobPreferences(preferred_titles=["Software Developer"])
    assert relevance_tier(_opp("Backend Developer"), prefs) == "related"


def test_role_unknown_to_the_taxonomy_never_produces_a_related_match() -> None:
    prefs = JobPreferences(preferred_titles=["Professional Dog Walker"])
    assert relevance_tier(_opp("Backend Developer"), prefs) == "none"
    assert relevance_tier(_opp("Professional Dog Walker"), prefs) == "exact"


def test_no_configured_role_is_always_exact_tier() -> None:
    assert relevance_tier(_opp("Barista"), JobPreferences()) == "exact"


def test_extra_related_terms_can_turn_a_none_into_a_related_match() -> None:
    prefs = JobPreferences(preferred_titles=["Professional Dog Walker"])
    opp = _opp("Cat Groomer")
    assert relevance_tier(opp, prefs) == "none"
    assert (
        relevance_tier(opp, prefs, extra_related_terms=frozenset({"groomer"}))
        == "related"
    )


def test_extra_related_terms_never_upgrade_a_match_to_exact() -> None:
    # Extra terms only ever widen the related tier -- a title that already
    # matches exactly stays exact regardless of what's passed in.
    prefs = JobPreferences(preferred_titles=["Software Engineer"])
    opp = _opp("Software Engineer")
    assert (
        relevance_tier(opp, prefs, extra_related_terms=frozenset({"software"}))
        == "exact"
    )


def test_blacklisted_company_is_none_tier_even_on_a_related_title_match() -> None:
    prefs = JobPreferences(
        preferred_titles=["Software Developer"], blacklisted_companies=["Evil Corp"]
    )
    opp = _opp("Backend Developer", company="Evil Corp")
    assert relevance_tier(opp, prefs) == "none"
