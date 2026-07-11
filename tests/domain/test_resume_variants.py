"""Phase 50 (ADR-0068): advisory, deterministic closest-variant selection."""

from __future__ import annotations

from career_agent.domain.models import TailoredContent, TailoredWorkEntry
from career_agent.domain.resume_variants import ResumeVariant, select_closest_variant


def _variant(id_: str, skills: list[str], category: str = "backend") -> ResumeVariant:
    return ResumeVariant(
        id=id_,
        category=category,
        profile_version="profile-v1",
        content=TailoredContent(summary="s", skills=skills),
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_empty_variant_list_returns_none() -> None:
    assert select_closest_variant([], "We need Python and Kubernetes.") is None


def test_picks_the_variant_with_more_overlapping_keywords() -> None:
    python_only = _variant("v1", ["Python"])
    python_and_k8s = _variant("v2", ["Python", "Kubernetes"])
    result = select_closest_variant(
        [python_only, python_and_k8s], "Looking for Python and Kubernetes experience."
    )
    assert result is not None
    assert result.id == "v2"


def test_ties_break_to_the_first_occurrence() -> None:
    first = _variant("v1", ["Python"])
    second = _variant("v2", ["Python"])
    result = select_closest_variant([first, second], "Looking for Python.")
    assert result is not None
    assert result.id == "v1"


def test_zero_overlap_still_returns_the_first_variant_not_none() -> None:
    only = _variant("v1", ["Python"])
    result = select_closest_variant([only], "We need a florist.")
    assert result is not None
    assert result.id == "v1"


def test_highlights_also_contribute_to_the_match() -> None:
    variant = ResumeVariant(
        id="v1",
        category="backend",
        profile_version="profile-v1",
        content=TailoredContent(
            summary="s",
            work=[
                TailoredWorkEntry(
                    source_entry_id="w1",
                    position="Engineer",
                    highlights=["shipped a distributed systems platform"],
                )
            ],
        ),
        created_at="2026-01-01T00:00:00+00:00",
    )
    no_match = _variant("v2", ["Ruby"])
    result = select_closest_variant(
        [no_match, variant], "Experience with distributed systems required."
    )
    assert result is not None
    assert result.id == "v1"
