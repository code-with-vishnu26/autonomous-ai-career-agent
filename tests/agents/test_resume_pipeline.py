"""Phase 8b / ADR-0023: ResumeTailoringPipeline composes generator -> gate
into an audited Application, plus a SubmittableApplication only when
approved -- and stops there, never calling an Applicator.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator, MissingSummaryError
from career_agent.agents.resume.pipeline import ResumeTailoringPipeline
from career_agent.core.bus import EventBus
from career_agent.core.events import Event, ResumeTailored, TruthfulnessRejected
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import (
    DraftedTailoring,
    Opportunity,
    Provenance,
    SubmittableApplication,
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


def _pipeline(
    drafted: DraftedTailoring, verdicts: dict[str, ClaimVerdict], bus: EventBus
) -> ResumeTailoringPipeline:
    generator = LLMResumeGenerator(FakeContentDrafter(drafted))
    gate = LLMTruthfulnessGate(FakeClaimVerifier(verdicts))
    return ResumeTailoringPipeline(generator, gate, bus)


class _Collector:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def __call__(self, event: Event) -> None:
        self.events.append(event)


async def test_an_approved_draft_produces_pending_plus_submittable() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    pipeline = _pipeline(
        _honest_drafted(),
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        },
        bus,
    )
    result = await pipeline.run(_opportunity(), profile)
    assert result.application.status == "pending"
    assert result.application.resume.truthfulness.approved is True
    assert isinstance(result.submittable, SubmittableApplication)


async def test_an_approved_draft_gets_a_full_rendered_text() -> None:
    """ADR-0025: rendered_text is computed here, at resume-creation time,
    once both content and profile are in scope -- and it must actually
    contain the real work history, not just the summary."""
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    pipeline = _pipeline(
        _honest_drafted(),
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        },
        bus,
    )
    result = await pipeline.run(_opportunity(), profile)
    rendered = result.application.resume.rendered_text
    assert rendered is not None
    assert "Backend engineer." in rendered
    assert "Software Engineer" in rendered
    assert "Built REST APIs serving 2M requests/day" in rendered
    assert "Python" in rendered


async def test_a_rejected_draft_produces_rejected_status_no_submittable() -> None:
    """The core proof: status is "rejected", not "failed" -- distinct from a
    submission failure, and no SubmittableApplication is ever produced."""
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    pipeline = _pipeline(
        DraftedTailoring(skills=["Kubernetes"]),  # not in profile.skills
        {},
        bus,
    )
    result = await pipeline.run(_opportunity(), profile)
    assert result.application.status == "rejected"
    assert result.application.status != "failed"
    assert result.application.resume.truthfulness.approved is False
    assert result.submittable is None
    # a rejected resume was never going to be submitted -- nothing to render
    assert result.application.resume.rendered_text is None


async def test_approval_publishes_resumetailored_not_truthfulnessrejected() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    collector = _Collector()
    bus.subscribe(Event, collector)
    pipeline = _pipeline(
        _honest_drafted(),
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        },
        bus,
    )
    result = await pipeline.run(_opportunity(), profile)
    assert len(collector.events) == 1
    published = collector.events[0]
    assert isinstance(published, ResumeTailored)
    assert published.resume_id == result.application.resume.id
    assert published.opportunity_id == "opp-1"


async def test_rejection_publishes_truthfulnessrejected_not_resumetailored() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    collector = _Collector()
    bus.subscribe(Event, collector)
    pipeline = _pipeline(DraftedTailoring(skills=["Kubernetes"]), {}, bus)
    await pipeline.run(_opportunity(), profile)
    assert len(collector.events) == 1
    published = collector.events[0]
    assert isinstance(published, TruthfulnessRejected)
    assert published.rejection_count == 1


async def test_a_missing_summary_propagates_and_publishes_no_event() -> None:
    """Precondition failures are not swallowed or converted into a rejected
    Application -- they propagate so the human can fix the actual problem."""
    profile = sample_master_profile()
    assert profile.basics.summary is None
    bus = EventBus()
    collector = _Collector()
    bus.subscribe(Event, collector)
    pipeline = _pipeline(_honest_drafted(), {}, bus)
    with pytest.raises(MissingSummaryError):
        await pipeline.run(_opportunity(), profile)
    assert collector.events == []


def test_pipeline_imports_no_applicator_type() -> None:
    """Canary for ADR-0023's scope boundary: ResumeTailoringPipeline imports
    neither Applicator nor ATSAdapter -- checked against the module's actual
    imports, not its prose, so a docstring explaining the boundary (which
    necessarily names both types) can't produce a false positive."""
    import ast
    import inspect

    from career_agent.agents.resume import pipeline as pipeline_module

    tree = ast.parse(inspect.getsource(pipeline_module))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
    assert "Applicator" not in imported_names
    assert "ATSAdapter" not in imported_names


async def test_artifacts_generated_for_approved_drafts_when_dir_set(
    tmp_path,
) -> None:
    """Phase 9 / ADR-0033: file artifacts are a derived cache computed here
    (same placement as rendered_text, ADR-0025), for approved drafts only,
    and only when the composition root opted in via artifacts_dir."""
    from pathlib import Path

    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
    gate = LLMTruthfulnessGate(
        FakeClaimVerifier(
            {
                "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
                "Built REST APIs serving 2M requests/day": ClaimVerdict(
                    verified=True, confidence=0.95
                ),
            }
        )
    )
    pipeline = ResumeTailoringPipeline(
        generator, gate, bus, artifacts_dir=tmp_path
    )
    result = await pipeline.run(_opportunity(), profile)

    artifacts = result.application.resume.artifacts
    formats = {a.format for a in artifacts}
    assert "docx" in formats  # always produced for an approved draft
    for artifact in artifacts:
        assert Path(artifact.path).exists()
        assert artifact.resume_id == result.application.resume.id
        assert artifact.profile_version == profile.version


async def test_no_artifacts_for_rejected_drafts_even_with_dir_set(
    tmp_path,
) -> None:
    """ADR-0044: ``_honest_drafted()``'s highlight is a verbatim restatement
    of the profile's own evidence, which the gate's Layer-1 precheck now
    confidently approves before the (fake) LLM is ever consulted -- so
    forcing a *rejection* to test this pipeline behavior needs a claim
    Layer 1 cannot resolve as safe. A named, unevidenced technology (AWS)
    is rejected deterministically, at Layer 1, without the fake verifier
    even being called."""
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    rejected_draft = DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Deployed the platform on AWS"],
            )
        ],
        skills=["Python"],
        projects=[],
    )
    generator = LLMResumeGenerator(FakeContentDrafter(rejected_draft))
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))
    pipeline = ResumeTailoringPipeline(
        generator, gate, bus, artifacts_dir=tmp_path
    )
    result = await pipeline.run(_opportunity(), profile)
    assert result.application.resume.artifacts == []
    assert list(tmp_path.iterdir()) == []  # nothing written at all


async def test_no_artifacts_when_dir_not_set_backward_compatible() -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    bus = EventBus()
    pipeline = _pipeline(
        _honest_drafted(),
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        },
        bus,
    )
    result = await pipeline.run(_opportunity(), profile)
    assert result.application.resume.artifacts == []
