"""ADR-0015/ADR-0019: the shared ATS URL pattern classifier."""

from __future__ import annotations

from career_agent.domain.ats_urls import match_ats_url, resolve_ats_kind


def test_matches_greenhouse() -> None:
    match = match_ats_url("https://boards.greenhouse.io/acme/jobs/12345")
    assert match == ("greenhouse", "acme", "12345")


def test_matches_lever() -> None:
    match = match_ats_url("https://jobs.lever.co/acme/abc-123")
    assert match == ("lever", "acme", "abc-123")


def test_matches_ashby() -> None:
    match = match_ats_url("https://jobs.ashbyhq.com/acme/xyz-789")
    assert match == ("ashby", "acme", "xyz-789")


def test_no_match_for_an_unrelated_url() -> None:
    assert match_ats_url("https://example.com/careers/some-job") is None


def test_resolve_ats_kind_returns_just_the_kind() -> None:
    assert resolve_ats_kind("https://boards.greenhouse.io/acme/jobs/12345") == (
        "greenhouse"
    )
    assert resolve_ats_kind("https://example.com/careers") is None
