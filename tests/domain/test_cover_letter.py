"""Phase 50 (ADR-0068): deterministic cover-letter assembly.

Every assertion checks the assembled body only ever contains sentences
already present in ``TailoredContent`` -- never anything new.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.cover_letter import assemble_cover_letter
from career_agent.domain.models import (
    Opportunity,
    Provenance,
    TailoredContent,
    TailoredWorkEntry,
)


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-1",
        company_id="acme",
        canonical_company="Acme Corp",
        title="Backend Engineer",
        source="ats_api",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://boards.greenhouse.io/acme/jobs/1",
            extraction_confidence=1.0,
        ),
        description_raw="We need a backend engineer with API experience.",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _content(highlights: list[str] | None = None) -> TailoredContent:
    return TailoredContent(
        summary="Backend engineer with 5 years of API experience.",
        work=[
            TailoredWorkEntry(
                source_entry_id="work-1",
                position="Software Engineer",
                highlights=highlights or ["Built REST APIs serving 2M requests/day"],
            )
        ],
        skills=["Python"],
    )


def test_body_contains_the_company_and_title() -> None:
    letter = assemble_cover_letter(
        _content(),
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    assert "Acme Corp" in letter.body
    assert "Backend Engineer" in letter.body


def test_body_contains_the_exact_summary_sentence() -> None:
    content = _content()
    letter = assemble_cover_letter(
        content,
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    assert content.summary in letter.body


def test_body_contains_the_exact_highlight_text() -> None:
    content = _content(["Led a migration to Kubernetes"])
    letter = assemble_cover_letter(
        content,
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    assert "Led a migration to Kubernetes" in letter.body


def test_no_highlights_produces_a_summary_only_letter() -> None:
    content = TailoredContent(summary="Backend engineer.", work=[])
    letter = assemble_cover_letter(
        content,
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    assert "Backend engineer." in letter.body
    assert "Relevant to this role" not in letter.body


def test_highlights_are_capped_at_three() -> None:
    content = _content(["One thing", "Two thing", "Three thing", "Four thing"])
    letter = assemble_cover_letter(
        content,
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    assert "One thing" in letter.body
    assert "Two thing" in letter.body
    assert "Three thing" in letter.body
    assert "Four thing" not in letter.body


def test_signed_with_the_applicant_name() -> None:
    letter = assemble_cover_letter(
        _content(),
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    assert letter.body.rstrip().endswith("Ada Lovelace")


def test_carries_opportunity_and_profile_identity() -> None:
    letter = assemble_cover_letter(
        _content(),
        _opportunity(),
        profile_version="profile-v7",
        applicant_name="Ada Lovelace",
    )
    assert letter.opportunity_id == "opp-1"
    assert letter.profile_version == "profile-v7"


def test_is_deterministic_for_the_same_input() -> None:
    first = assemble_cover_letter(
        _content(),
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    second = assemble_cover_letter(
        _content(),
        _opportunity(),
        profile_version="profile-v1",
        applicant_name="Ada Lovelace",
    )
    assert first.body == second.body
