"""Phase 50 (ADR-0068): ResumeVariantEngine composes an unmodified
ResumeTailoringPipeline with advisory variant selection and cover-letter
assembly. Nothing here submits anything, and a rejected draft is never
memorized as a reusable variant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator
from career_agent.agents.resume.materials import ResumeVariantEngine
from career_agent.agents.resume.pipeline import ResumeTailoringPipeline
from career_agent.core.bus import EventBus
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import (
    DraftedTailoring,
    Opportunity,
    Provenance,
    TailoredWorkEntry,
)
from career_agent.domain.resume_variants import ResumeVariant
from tests._fakes import FakeClaimVerifier, FakeContentDrafter

from ._profile_fixture import sample_master_profile


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-1",
        company_id="acme",
        canonical_company="Acme Corp",
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


def _honest_drafted() -> DraftedTailoring:
    return DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            )
        ],
        skills=["Python"],
        projects=[],
    )


def _engine(
    drafted: DraftedTailoring, verdicts: dict[str, ClaimVerdict]
) -> ResumeVariantEngine:
    generator = LLMResumeGenerator(FakeContentDrafter(drafted))
    gate = LLMTruthfulnessGate(FakeClaimVerifier(verdicts))
    pipeline = ResumeTailoringPipeline(generator, gate, EventBus())
    return ResumeVariantEngine(pipeline)


async def test_approved_draft_produces_cover_letter_and_new_variant() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    engine = _engine(
        _honest_drafted(),
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        },
    )
    materials = await engine.prepare(_opportunity(), profile, category="backend")
    assert materials.tailoring.application.status == "pending"
    assert materials.cover_letter is not None
    assert "Acme Corp" in materials.cover_letter.body
    assert materials.new_variant is not None
    assert materials.new_variant.category == "backend"
    resume_content = materials.tailoring.application.resume.content
    assert materials.new_variant.content == resume_content


async def test_rejected_draft_produces_no_cover_letter_and_no_new_variant() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    engine = _engine(DraftedTailoring(skills=["Kubernetes"]), {})
    materials = await engine.prepare(_opportunity(), profile, category="backend")
    assert materials.tailoring.application.status == "rejected"
    assert materials.cover_letter is None
    assert materials.new_variant is None


async def test_prior_variants_only_affect_the_advisory_field() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    engine = _engine(
        _honest_drafted(),
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        },
    )
    from career_agent.domain.models import TailoredContent

    prior = ResumeVariant(
        id="prior-1",
        category="backend",
        profile_version="profile-v1",
        content=TailoredContent(summary="s", skills=["Python"]),
        created_at="2026-01-01T00:00:00+00:00",
    )
    materials = await engine.prepare(
        _opportunity(), profile, category="backend", prior_variants=[prior]
    )
    assert materials.closest_prior_variant == prior
    # the pipeline's own gated output is unaffected by the prior variant
    assert materials.tailoring.application.status == "pending"


async def test_no_prior_variants_leaves_closest_prior_variant_none() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    engine = _engine(
        _honest_drafted(),
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        },
    )
    materials = await engine.prepare(_opportunity(), profile, category="backend")
    assert materials.closest_prior_variant is None


def test_materials_module_imports_no_storage() -> None:
    """Canary (Phase 50, ADR-0068): mirrors pipeline.py's own no-Applicator
    canary -- this module composes only agents/domain, never storage/;
    persistence stays the caller's job, same as SqliteApplicationStore."""
    import ast
    import inspect

    from career_agent.agents.resume import materials as materials_module

    tree = ast.parse(inspect.getsource(materials_module))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any(mod.startswith("career_agent.storage") for mod in imported_modules)
