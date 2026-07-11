"""Phase 46 (ADR-0064): JobPreferences model + query-generation guards.

No I/O, no network -- pure model validation and the deterministic
``generate_search_queries`` algorithm.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from career_agent.domain.job_preferences import (
    JobPreferences,
    generate_search_queries,
)


def test_every_field_defaults_to_no_constraint() -> None:
    """An absent preference means 'no constraint,' never an implicit
    exclusion -- every list defaults empty, every optional defaults None."""
    prefs = JobPreferences()
    assert prefs.preferred_titles == []
    assert prefs.countries == []
    assert prefs.visa_sponsorship_required is None
    assert prefs.max_applications_per_day is None
    assert prefs.require_human_confirmation is True
    assert prefs.auto_generate_cover_letter is False


def test_rejects_unrecognized_seniority_employment_type_and_work_mode() -> None:
    with pytest.raises(ValidationError):
        JobPreferences(seniority="ultra-senior")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        JobPreferences(employment_types=["gig"])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        JobPreferences(work_mode=["telepathic"])  # type: ignore[list-item]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"experience_years_min": -1},
        {"experience_years_max": -1},
        {"experience_years_min": 5, "experience_years_max": 2},
        {"salary_min": -1.0},
        {"salary_max": -1.0},
        {"salary_min": 12.0, "salary_max": 6.0},
        {"max_applications_per_day": 0},
    ],
)
def test_rejects_invalid_ranges(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        JobPreferences(**kwargs)  # type: ignore[arg-type]


def test_max_applications_per_day_one_is_the_valid_boundary() -> None:
    assert JobPreferences(max_applications_per_day=1).max_applications_per_day == 1


def test_generate_search_queries_returns_empty_with_no_titles() -> None:
    """No titles configured means nothing to search for -- an empty list,
    not an error and not a wildcard search."""
    prefs = JobPreferences(countries=["India"], work_mode=["remote"])
    assert generate_search_queries(prefs) == []


def test_generate_search_queries_combines_titles_and_locations() -> None:
    prefs = JobPreferences(
        preferred_titles=["Backend Developer", "Python Developer"],
        work_mode=["remote"],
        countries=["India"],
    )
    queries = generate_search_queries(prefs)
    assert queries == [
        "Backend Developer Remote",
        "Backend Developer India",
        "Python Developer Remote",
        "Python Developer India",
    ]


def test_generate_search_queries_merges_preferred_and_alternative_titles() -> None:
    prefs = JobPreferences(
        preferred_titles=["Backend Developer"],
        alternative_titles=["Software Engineer"],
    )
    queries = generate_search_queries(prefs)
    assert queries == ["Backend Developer", "Software Engineer"]


def test_generate_search_queries_falls_back_to_bare_title_with_no_location() -> None:
    prefs = JobPreferences(preferred_titles=["AI Engineer"])
    assert generate_search_queries(prefs) == ["AI Engineer"]


def test_generate_search_queries_deduplicates_titles_and_queries() -> None:
    prefs = JobPreferences(
        preferred_titles=["Backend Developer", "backend developer  "],
        alternative_titles=["Backend Developer"],
    )
    # Whitespace-only variance collapses; exact-string dedup keeps distinct
    # casing (case-folding titles would be a different, larger decision).
    queries = generate_search_queries(prefs)
    assert queries.count("Backend Developer") == 1


def test_generate_search_queries_respects_max_queries_cap() -> None:
    prefs = JobPreferences(
        preferred_titles=["A", "B", "C"],
        countries=["X", "Y", "Z"],
    )
    queries = generate_search_queries(prefs, max_queries=2)
    assert len(queries) == 2
    assert queries == ["A X", "A Y"]


def test_generate_search_queries_drops_queries_matching_excluded_keywords() -> None:
    """A query must never be generated for a title/location combo containing
    a keyword the user explicitly excluded."""
    prefs = JobPreferences(
        preferred_titles=["Senior Backend Developer", "Backend Developer"],
        countries=["India"],
        keywords_exclude=["senior"],
    )
    queries = generate_search_queries(prefs)
    assert not any("senior" in q.lower() for q in queries)
    assert "Backend Developer India" in queries


def test_generate_search_queries_is_deterministic() -> None:
    prefs = JobPreferences(
        preferred_titles=["Backend Developer"], countries=["India", "UK"]
    )
    assert generate_search_queries(prefs) == generate_search_queries(prefs)
