"""Phase 8a / ADR-0022: LLMResumeGenerator -- summary sourced structurally,
never drafted; a missing summary is a loud rejection, not a silent fallback;
no self-verification (the gate is the sole backstop).
"""

from __future__ import annotations

import pytest

from career_agent.agents.resume.generator import LLMResumeGenerator, MissingSummaryError
from career_agent.domain.models import (
    DraftedTailoring,
    Opportunity,
    Provenance,
    TailoredProjectEntry,
    TailoredWorkEntry,
)
from tests._fakes import FakeContentDrafter

from ._profile_fixture import sample_master_profile


def _opportunity() -> Opportunity:
    from datetime import UTC, datetime

    return Opportunity(
        id="opp-1",
        company_id="acme",
        canonical_company="acme.com",
        title="Software Engineer",
        source="ats_api",
        source_url="https://boards.greenhouse.io/acme/jobs/12345",
        provenance=Provenance(
            method="structured_api",
            reference="https://boards.greenhouse.io/acme/jobs/12345",
            extraction_confidence=1.0,
        ),
        description_raw="We are hiring a backend engineer with API experience.",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _drafted() -> DraftedTailoring:
    return DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            )
        ],
        skills=["Python", "Django"],
        projects=[
            TailoredProjectEntry(
                source_entry_id="proj-internal",
                name="Internal Tool",
                highlights=["Built an internal tool"],
            )
        ],
    )


async def test_missing_summary_is_rejected_before_the_drafter_is_ever_called() -> None:
    """The load-bearing test: no LLM call happens for a profile with no
    summary -- proven by an empty call log, not just an exception."""
    profile = sample_master_profile()
    assert profile.basics.summary is None
    drafter = FakeContentDrafter(_drafted())
    generator = LLMResumeGenerator(drafter)
    with pytest.raises(MissingSummaryError):
        await generator.tailor(_opportunity(), profile)
    assert drafter.calls == []


async def test_missing_summary_rejects_whitespace_only_too() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "   "
    drafter = FakeContentDrafter(_drafted())
    generator = LLMResumeGenerator(drafter)
    with pytest.raises(MissingSummaryError):
        await generator.tailor(_opportunity(), profile)
    assert drafter.calls == []


async def test_summary_is_sourced_from_profile_never_from_the_drafter() -> None:
    """DraftedTailoring has no summary field at all -- the generator must
    source it from profile.basics.summary and nowhere else."""
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer with 3 years of API experience."
    drafter = FakeContentDrafter(_drafted())
    generator = LLMResumeGenerator(drafter)
    draft = await generator.tailor(_opportunity(), profile)
    assert draft.content.summary == "Backend engineer with 3 years of API experience."


async def test_tailor_assembles_work_skills_projects_from_the_drafter() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    drafter = FakeContentDrafter(_drafted())
    generator = LLMResumeGenerator(drafter)
    draft = await generator.tailor(_opportunity(), profile)
    assert draft.opportunity_id == "opp-1"
    assert draft.profile_version == profile.version
    assert draft.content.work[0].source_entry_id == "work-techco"
    assert draft.content.skills == ["Python", "Django"]
    assert draft.content.projects[0].name == "Internal Tool"


async def test_a_drafter_failure_propagates_instead_of_a_fabricated_draft() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    drafter = FakeContentDrafter(TimeoutError("simulated drafter timeout"))
    generator = LLMResumeGenerator(drafter)
    with pytest.raises(TimeoutError):
        await generator.tailor(_opportunity(), profile)


def test_drafted_tailoring_cannot_carry_a_summary_at_all() -> None:
    """Canary: the structural guarantee this ADR relies on -- DraftedTailoring
    has no summary field, so no drafter implementation can slip one in."""
    assert set(DraftedTailoring.model_fields) == {"work", "skills", "projects"}
