"""Phase 8c / ADR-0024: SubmissionPipeline composes a real Applicator with a
real confirmation source for the first time -- every prior phase proved
this chain against fakes on both sides at once; here the confirmation side
is the real cli.confirm_submission shape (a plain callable), exercised
against a real TieredApplicator.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.agents.apply.applicator import TieredApplicator
from career_agent.agents.apply.pipeline import SubmissionPipeline
from career_agent.core.events import ApplicationSubmitted
from career_agent.domain.models import (
    Application,
    BasicsSection,
    HumanConfirmation,
    LegalStatusSection,
    Opportunity,
    Provenance,
    Statement,
    SubmittableApplication,
    TailoredContent,
    TailoredResume,
    TruthfulnessResult,
)
from career_agent.storage.memory import InMemoryOpportunityRepository
from tests._fakes import FakeATSAdapter


def _approved_application(opportunity_id: str = "opp-1") -> SubmittableApplication:
    resume = TailoredResume(
        id="resume-1",
        opportunity_id=opportunity_id,
        profile_version="profile-v1",
        content=TailoredContent(summary="x"),
        truthfulness=TruthfulnessResult(
            profile_version="profile-v1",
            approved=True,
            statements=[
                Statement(text="x", evidence=None, confidence=0.9, verified=True)
            ],
            prompt_version="test-v1",
        ),
    )
    app = Application(
        id="app-1",
        opportunity_id=opportunity_id,
        resume=resume,
        applicant=BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        legal_status=LegalStatusSection(),
        status="pending",
    )
    return SubmittableApplication(application=app)


async def _pipeline() -> tuple[TieredApplicator, FakeATSAdapter]:
    adapter = FakeATSAdapter(ats_kind="greenhouse")
    repo = InMemoryOpportunityRepository()
    await repo.add(
        Opportunity(
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
            description_raw="",
            discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    applicator = TieredApplicator({"greenhouse": adapter}, repo)
    return applicator, adapter


def _yes_confirm():
    def _confirm(preview):
        return HumanConfirmation(
            preview_token=preview.preview_token,
            confirmed_by="test-user",
            confirmed_at=datetime.now(UTC),
        )

    return _confirm


def _no_confirm(preview):
    return None


async def test_a_granted_confirmation_submits_through_the_real_applicator() -> None:
    applicator, adapter = await _pipeline()
    pipeline = SubmissionPipeline(applicator, _yes_confirm())
    event = await pipeline.run(_approved_application())
    assert isinstance(event, ApplicationSubmitted)
    assert len(adapter.calls) == 1


async def test_a_declined_confirmation_never_calls_submit() -> None:
    """The load-bearing test: a human declining must never let the adapter
    be reached -- the same adapter.calls == [] proof as 7a, now driven by
    a real confirmation source's negative answer, not a token mismatch."""
    applicator, adapter = await _pipeline()
    pipeline = SubmissionPipeline(applicator, _no_confirm)
    result = await pipeline.run(_approved_application())
    assert result is None
    assert adapter.calls == []


async def test_confirm_is_handed_the_exact_preview_prepare_issued() -> None:
    applicator, _adapter = await _pipeline()
    seen_previews = []

    def _capturing_confirm(preview):
        seen_previews.append(preview)
        return HumanConfirmation(
            preview_token=preview.preview_token,
            confirmed_by="test-user",
            confirmed_at=datetime.now(UTC),
        )

    pipeline = SubmissionPipeline(applicator, _capturing_confirm)
    await pipeline.run(_approved_application())
    assert len(seen_previews) == 1
    assert seen_previews[0].application_id == "app-1"


async def test_cli_confirm_submission_composes_with_the_real_pipeline() -> None:
    """Proves the actual shape from cli.py, not a hand-rolled stand-in,
    drives a real Applicator end to end."""
    from career_agent.cli import confirm_submission

    applicator, adapter = await _pipeline()

    def _confirm(preview):
        return confirm_submission(preview, input_fn=lambda _: "y")

    pipeline = SubmissionPipeline(applicator, _confirm)
    event = await pipeline.run(_approved_application())
    assert isinstance(event, ApplicationSubmitted)
    assert len(adapter.calls) == 1


async def test_cli_confirm_submission_declining_never_reaches_the_adapter() -> None:
    from career_agent.cli import confirm_submission

    applicator, adapter = await _pipeline()

    def _confirm(preview):
        return confirm_submission(preview, input_fn=lambda _: "")

    pipeline = SubmissionPipeline(applicator, _confirm)
    result = await pipeline.run(_approved_application())
    assert result is None
    assert adapter.calls == []
