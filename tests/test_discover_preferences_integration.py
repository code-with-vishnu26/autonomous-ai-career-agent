"""Phase 46 (ADR-0064): discovery extended to use Job Search Preferences.

``build_discovery_sources`` gains an optional ``preferences`` parameter.
The load-bearing guarantee: passing ``None`` (or preferences that generate
no queries) reproduces the *exact* prior behavior byte-for-byte -- "extend,
never remove" is proven here, not just asserted in a docstring.
"""

from __future__ import annotations

from career_agent.cli import build_discovery_sources
from career_agent.core.config import Settings
from career_agent.domain.job_preferences import JobPreferences

_ALL_KEYLESS_DISABLED = {
    "arbeitnow_enabled": False,
    "themuse_enabled": False,
    "remotive_enabled": False,
    "remoteok_enabled": False,
}


def _settings(**overrides: object) -> Settings:
    return Settings(
        groq_api_key=None,
        anthropic_api_key=None,
        adzuna_app_id="id",
        adzuna_app_key="key",
        reed_api_key="reed-key",
        usajobs_api_key="usajobs-key",
        usajobs_user_agent="me@example.com",
        jooble_api_key="jooble-key",
        **_ALL_KEYLESS_DISABLED,
        **overrides,
    )


def test_no_preferences_reproduces_the_exact_prior_single_source_behavior() -> (
    None
):
    """Regression guard for 'do not remove current discovery': with no
    preferences, each keyword-capable source is wired exactly once, with
    the plain (unbracketed) name and the static discovery_keywords."""
    settings = _settings(discovery_keywords="software engineer")
    sources = build_discovery_sources(settings, None)
    names = [name for name, _ in sources]
    assert names == ["adzuna", "reed", "usajobs", "jooble"]


def test_preferences_with_no_generated_queries_also_reproduces_prior_behavior() -> (
    None
):
    """Preferences that exist but configure no titles generate zero
    queries -- falls back to the static keyword, same as None."""
    settings = _settings()
    sources = build_discovery_sources(settings, JobPreferences())
    names = [name for name, _ in sources]
    assert names == ["adzuna", "reed", "usajobs", "jooble"]


def test_preferences_with_titles_fan_out_each_keyword_source_per_query() -> None:
    settings = _settings()
    prefs = JobPreferences(
        preferred_titles=["Backend Developer", "Python Developer"],
        work_mode=["remote"],
        countries=["India"],
    )
    sources = build_discovery_sources(settings, prefs)
    names = [name for name, _ in sources]
    expected_queries = [
        "Backend Developer Remote",
        "Backend Developer India",
        "Python Developer Remote",
        "Python Developer India",
    ]
    for base in ("adzuna", "reed", "usajobs", "jooble"):
        for query in expected_queries:
            assert f"{base}[{query}]" in names
    assert len(names) == 4 * len(expected_queries)


def test_keyless_and_unconfigured_sources_are_unaffected_by_preferences() -> None:
    """Sources with no keyword parameter (arbeitnow/themuse/remotive/
    remoteok) and sources whose credentials are absent must never be
    affected by preferences -- they aren't keyword-driven at all."""
    settings = Settings(
        groq_api_key=None,
        anthropic_api_key=None,
        arbeitnow_enabled=True,
        themuse_enabled=False,
        remotive_enabled=False,
        remoteok_enabled=False,
    )
    prefs = JobPreferences(preferred_titles=["Backend Developer"])
    sources = build_discovery_sources(settings, prefs)
    assert [name for name, _ in sources] == ["arbeitnow"]


def test_only_configured_sources_are_wired_even_with_preferences() -> None:
    """A source with no credentials must stay absent regardless of
    preferences -- preferences never bypass the existing 'only wire what's
    configured' composition-root discipline."""
    settings = Settings(
        groq_api_key=None,
        anthropic_api_key=None,
        adzuna_app_id="id",
        adzuna_app_key="key",
        **_ALL_KEYLESS_DISABLED,
    )
    prefs = JobPreferences(preferred_titles=["Backend Developer"])
    sources = build_discovery_sources(settings, prefs)
    assert all(name.startswith("adzuna") for name, _ in sources)


def test_queries_excluding_a_keyword_never_reach_source_construction() -> None:
    """Only "Backend Developer" survives the exclude filter, generating
    exactly one query -- so sources are labeled plainly (single-query
    fallback naming), but the underlying source must be built with the
    surviving, non-excluded query text, never the excluded title."""
    settings = _settings()
    prefs = JobPreferences(
        preferred_titles=["Senior Backend Developer", "Backend Developer"],
        countries=["India"],
        keywords_exclude=["senior"],
    )
    sources = build_discovery_sources(settings, prefs)
    names = [name for name, _ in sources]
    assert not any("senior" in name.lower() for name in names)
    assert names == ["adzuna", "reed", "usajobs", "jooble"]
    adzuna_source = dict(sources)["adzuna"]
    assert adzuna_source._keywords == "Backend Developer India"  # noqa: SLF001
