"""Phase 8a / ADR-0022: the first integration point between two
independently-built components -- LLMResumeGenerator's real output shape
fed into the real LLMTruthfulnessGate (Phase 5), not two components tested
only in isolation against hand-authored fixtures on each side.

LLM boundaries are still fakes (FakeContentDrafter, FakeClaimVerifier) --
this proves the generator's and gate's *own* code compose correctly
(field names line up, source_entry_id resolves, the gate's evidence
assembly can actually read what the generator assembled), not that a real
model drafts or judges correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import (
    DraftedTailoring,
    Opportunity,
    Provenance,
    TailoredProjectEntry,
    TailoredWorkEntry,
)
from tests._fakes import FakeClaimVerifier, FakeContentDrafter

from ._profile_fixture import sample_master_profile


def _opportunity() -> Opportunity:
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


async def test_an_honest_generated_draft_is_approved_end_to_end() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer with strong API experience."
    drafted = DraftedTailoring(
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
    generator = LLMResumeGenerator(FakeContentDrafter(drafted))
    draft = await generator.tailor(_opportunity(), profile)

    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
            "Built an internal tool": ClaimVerdict(verified=True, confidence=0.9),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    result = await gate.verify(draft, profile)

    assert result.approved is True
    assert result.rejections == []


async def test_a_generated_draft_with_a_hallucinated_skill_is_blocked_end_to_end() -> (
    None
):
    """Proves the seam works for the failure path too -- a drafted skill not
    in profile.skills is caught by the gate's structural check, with no
    model call needed, exactly as it would be for a hand-authored draft."""
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    # "Kubernetes" is not in the profile's skills list.
    drafted = DraftedTailoring(skills=["Python", "Kubernetes"])
    generator = LLMResumeGenerator(FakeContentDrafter(drafted))
    draft = await generator.tailor(_opportunity(), profile)

    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))  # no LLM call needed: structural
    result = await gate.verify(draft, profile)

    assert result.approved is False
    assert result.rejections[0].category == "skill_not_found"
    assert "Kubernetes" in result.rejections[0].detail


async def test_a_generated_draft_referencing_an_unknown_work_entry_is_blocked() -> None:
    """Proves the seam works even if a drafter hallucinates a source_entry_id
    -- caught the same way a hand-authored bad draft would be (ADR-0018's
    Case #4 precedent), no special-casing needed for generator output."""
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    drafted = DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-does-not-exist",
                position="Staff Engineer",
                highlights=["Led a major initiative"],
            )
        ]
    )
    generator = LLMResumeGenerator(FakeContentDrafter(drafted))
    draft = await generator.tailor(_opportunity(), profile)

    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))
    result = await gate.verify(draft, profile)

    assert result.approved is False
    assert result.rejections[0].category == "employer_mismatch"
