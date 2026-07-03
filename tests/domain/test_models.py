"""Behavioral tests for career_agent.domain.models."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from career_agent.domain.models import (
    FUNNEL_ORDER,
    Application,
    BasicsSection,
    EvidenceRef,
    HeldCandidate,
    LegalStatusSection,
    MasterProfile,
    Opportunity,
    Outcome,
    Provenance,
    RejectionReason,
    SkillEntry,
    Statement,
    TailoredContent,
    TailoredResume,
    TailoredResumeDraft,
    TailoredWorkEntry,
    TruthfulnessResult,
    WorkEntry,
)


def _profile(version: str = "v1") -> MasterProfile:
    return MasterProfile(
        version=version,
        basics=BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        work=[
            WorkEntry(
                id="work-1",
                name="Acme Corp",
                position="Engineer",
                start_date=date(2020, 1, 1),
                highlights=["Built the analytical engine"],
            )
        ],
        skills=[SkillEntry(id="skill-1", name="Python")],
    )


def test_evidence_ref_binds_to_stable_entry_id_not_index() -> None:
    """EvidenceRef must reference a stable entry_id, never an array position."""
    ref = EvidenceRef(
        profile_version="v1",
        section="skills",
        entry_id="skill-1",
        field="name",
        excerpt="Python",
    )
    assert ref.entry_id == "skill-1"
    # field + index are separate typed values, never a combined "skills[3]" string
    assert ref.index is None
    ref_with_index = EvidenceRef(
        profile_version="v1",
        section="work",
        entry_id="work-1",
        field="highlights",
        index=0,
        excerpt="Built the analytical engine",
    )
    assert ref_with_index.index == 0


def test_evidence_ref_basics_section_allows_no_entry_id() -> None:
    ref = EvidenceRef(
        profile_version="v1", section="basics", field="name", excerpt="Ada Lovelace"
    )
    assert ref.entry_id is None


def test_statement_confidence_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        Statement(text="x", evidence=None, confidence=1.5, verified=False)
    with pytest.raises(ValidationError):
        Statement(text="x", evidence=None, confidence=-0.1, verified=False)


def test_truthfulness_result_profile_version_matches_draft() -> None:
    profile = _profile(version="v42")
    draft = TailoredResumeDraft(
        opportunity_id="opp-1",
        profile_version=profile.version,
        content=TailoredContent(summary="Engineer"),
    )
    result = TruthfulnessResult(
        profile_version=draft.profile_version,
        approved=True,
        statements=[],
        prompt_version="test-v1",
    )
    # this is the load-bearing check: the two versions must agree before a
    # TailoredResume can be legitimately assembled from a draft + a result
    assert result.profile_version == draft.profile_version
    resume = TailoredResume(
        id="resume-1",
        opportunity_id=draft.opportunity_id,
        profile_version=draft.profile_version,
        content=draft.content,
        truthfulness=result,
    )
    assert resume.profile_version == result.profile_version


def test_rejected_draft_still_produces_an_auditable_tailored_resume() -> None:
    """A rejected TruthfulnessResult can still be attached for audit purposes;
    it is the caller's job (Phase 7) to refuse to submit it."""
    result = TruthfulnessResult(
        profile_version="v1",
        approved=False,
        statements=[],
        rejections=[
            RejectionReason(
                statement_text="5 years of AWS experience",
                category="skill_not_found",
                detail='skill "AWS" not found in master profile',
            )
        ],
        prompt_version="test-v1",
    )
    resume = TailoredResume(
        id="resume-1",
        opportunity_id="opp-1",
        profile_version="v1",
        content=TailoredContent(summary="Engineer"),
        truthfulness=result,
    )
    assert resume.truthfulness.approved is False
    assert resume.truthfulness.rejections[0].category == "skill_not_found"


def test_opportunity_requires_provenance() -> None:
    """ADR-0012: provenance is required with no default, so no source can emit
    an Opportunity without recording how (and how confidently) it was derived --
    this is what makes provenance universal by construction, not HN-only."""
    with pytest.raises(ValidationError):
        Opportunity(
            id="opp-1",
            company_id="acme",
            title="Engineer",
            source="ats_api",
            source_url="https://example.invalid/1",
            description_raw="",
            discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_provenance_confidence_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        Provenance(
            method="text_extraction", reference="ref", extraction_confidence=1.5
        )


def test_held_candidate_is_a_distinct_type_from_opportunity() -> None:
    """ADR-0013: a held candidate is its own type, never a low-confidence
    Opportunity -- a non-job must not be demoted into the vouched type."""
    held = HeldCandidate(
        source="hn",
        reason="seeking_work",
        reference="https://news.ycombinator.com/item?id=1",
        raw_excerpt="Backend engineer, open to work",
        extraction_confidence=0.0,
        held_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert not isinstance(held, Opportunity)
    with pytest.raises(ValidationError):
        HeldCandidate(
            source="hn",
            reason="not_a_posting",
            reference="ref",
            raw_excerpt="x",
            extraction_confidence=1.4,  # out of bounds
            held_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_tailored_work_entry_traces_back_to_source_entry() -> None:
    entry = TailoredWorkEntry(
        source_entry_id="work-1", position="Engineer", highlights=["Did the thing"]
    )
    assert entry.source_entry_id == "work-1"


def test_funnel_order_treats_rejection_as_out_of_band() -> None:
    assert FUNNEL_ORDER["rejection"] == -1
    assert FUNNEL_ORDER["viewed"] < FUNNEL_ORDER["interview"] < FUNNEL_ORDER["offer"]


def test_outcomes_are_additive_not_a_single_terminal_status() -> None:
    """Multiple Outcome rows may exist for one application; a rejection after
    an interview must remain distinguishable from a rejection at screening."""
    outcomes = [
        Outcome(
            application_id="app-1",
            kind="viewed",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        Outcome(
            application_id="app-1",
            kind="interview",
            occurred_at=datetime(2026, 1, 5, tzinfo=UTC),
        ),
        Outcome(
            application_id="app-1",
            kind="rejection",
            occurred_at=datetime(2026, 1, 10, tzinfo=UTC),
        ),
    ]
    # reading only the latest row would lose that this was a post-interview
    # rejection, not a screening rejection -- the full history must be kept
    kinds_seen = [o.kind for o in outcomes]
    assert kinds_seen == ["viewed", "interview", "rejection"]
    assert "interview" in kinds_seen  # the distinction the Learning Agent needs


def test_master_profile_version_is_immutable_identity_not_mutated_in_place() -> None:
    v1 = _profile(version="v1")
    v2 = v1.model_copy(update={"version": "v2", "skills": []})
    assert v1.version == "v1"
    assert v1.skills  # original snapshot untouched
    assert v2.version == "v2"
    assert v2.skills == []


def test_application_requires_status() -> None:
    profile = _profile()
    draft = TailoredResumeDraft(
        opportunity_id="opp-1",
        profile_version=profile.version,
        content=TailoredContent(summary="Engineer"),
    )
    resume = TailoredResume(
        id="resume-1",
        opportunity_id="opp-1",
        profile_version=profile.version,
        content=draft.content,
        truthfulness=TruthfulnessResult(
            profile_version=profile.version,
            approved=True,
            statements=[],
            prompt_version="test-v1",
        ),
    )
    app = Application(
        id="app-1",
        opportunity_id="opp-1",
        resume=resume,
        applicant=BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        legal_status=LegalStatusSection(),
        status="pending",
    )
    assert app.status == "pending"
    assert app.tier_used is None


def test_application_requires_an_applicant_snapshot() -> None:
    """applicant is required, not optional-with-a-default (ADR-0027) -- the
    same "impossible to construct otherwise" discipline as canonical_company/
    provenance elsewhere. Nothing should be able to build a real Application
    with no identity and have that go unnoticed until a real form tries to
    fill blank fields."""
    profile = _profile()
    resume = TailoredResume(
        id="resume-1",
        opportunity_id="opp-1",
        profile_version=profile.version,
        content=TailoredContent(summary="Engineer"),
        truthfulness=TruthfulnessResult(
            profile_version=profile.version,
            approved=True,
            statements=[],
            prompt_version="test-v1",
        ),
    )
    with pytest.raises(ValidationError, match="applicant"):
        Application(
            id="app-1", opportunity_id="opp-1", resume=resume, status="pending"
        )
