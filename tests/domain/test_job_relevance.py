"""Phase 70: role-relevance filtering for discovered opportunities."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.domain.job_preferences import JobPreferences
from career_agent.domain.job_relevance import matches_search, role_terms
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
