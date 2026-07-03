"""Phase 7b4 / ADR-0021: EmailApplicator never claims a send happened, and
confirmation-token binding gates draft creation the same way it gates
Tier 1/2 submission.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.agents.apply.email_applicator import EmailApplicator
from career_agent.core.events import HumanActionRequired
from career_agent.domain.models import (
    Application,
    BasicsSection,
    HumanConfirmation,
    LegalStatusSection,
    Opportunity,
    Provenance,
    Statement,
    SubmissionPreview,
    SubmittableApplication,
    TailoredContent,
    TailoredResume,
    TruthfulnessResult,
)
from career_agent.storage.memory import InMemoryOpportunityRepository
from tests._fakes import FakeEmailDraftSink


def _opportunity(opportunity_id: str, source_url: str) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="acme.com",
        title="Software Engineer",
        source="career_page",
        source_url=source_url,
        provenance=Provenance(
            method="text_extraction", reference=source_url, extraction_confidence=0.6
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _approved_application(opportunity_id: str) -> SubmittableApplication:
    resume = TailoredResume(
        id="resume-1",
        opportunity_id=opportunity_id,
        profile_version="profile-v1",
        content=TailoredContent(summary="Experienced engineer."),
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


def _confirmation(preview_token: str) -> HumanConfirmation:
    return HumanConfirmation(
        preview_token=preview_token,
        confirmed_by="test-user",
        confirmed_at=datetime.now(UTC),
    )


async def _applicator(
    opportunity: Opportunity,
) -> tuple[EmailApplicator, FakeEmailDraftSink]:
    repo = InMemoryOpportunityRepository()
    await repo.add(opportunity)
    sink = FakeEmailDraftSink()
    return EmailApplicator(sink, repo), sink


async def test_prepare_performs_no_draft_creation() -> None:
    opportunity = _opportunity("opp-1", "jobs@acme.com")
    applicator, sink = await _applicator(opportunity)
    await applicator.prepare(_approved_application("opp-1"))
    assert sink.calls == []


async def test_submit_creates_a_draft_and_never_claims_submission() -> None:
    """The core proof: this tier can only ever say a human action is
    required -- it must not return ApplicationSubmitted, because nothing
    was sent."""
    opportunity = _opportunity("opp-1", "jobs@acme.com")
    applicator, sink = await _applicator(opportunity)
    preview = await applicator.prepare(_approved_application("opp-1"))
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, HumanActionRequired)
    assert event.reason == "confirmation"
    assert len(sink.calls) == 1
    assert sink.calls[0]["to"] == "jobs@acme.com"


async def test_mismatched_confirmation_token_never_creates_a_draft() -> None:
    """Same shape as the Tier 1/2 proof: adapter.calls stays empty, not
    just 'an exception was raised somewhere.'"""
    opportunity = _opportunity("opp-1", "jobs@acme.com")
    applicator, sink = await _applicator(opportunity)
    preview = await applicator.prepare(_approved_application("opp-1"))
    with pytest.raises(ValueError, match="confirmation"):
        await applicator.submit(preview, _confirmation("a-different-token"))
    assert sink.calls == []


async def test_unknown_preview_token_never_creates_a_draft() -> None:
    opportunity = _opportunity("opp-1", "jobs@acme.com")
    applicator, sink = await _applicator(opportunity)
    forged_preview = SubmissionPreview(
        application_id="app-1",
        tier="email",
        target="jobs@acme.com",
        rendered_content="x",
        preview_token="never-issued",
    )
    with pytest.raises(ValueError, match="unknown"):
        await applicator.submit(forged_preview, _confirmation("never-issued"))
    assert sink.calls == []


async def test_a_confirmed_token_cannot_be_replayed() -> None:
    opportunity = _opportunity("opp-1", "jobs@acme.com")
    applicator, sink = await _applicator(opportunity)
    preview = await applicator.prepare(_approved_application("opp-1"))
    confirmation = _confirmation(preview.preview_token)
    await applicator.submit(preview, confirmation)
    assert len(sink.calls) == 1
    with pytest.raises(ValueError, match="unknown"):
        await applicator.submit(preview, confirmation)
    assert len(sink.calls) == 1


async def test_email_draft_sink_protocol_has_no_send_method() -> None:
    """Canary for ADR-0021: the scope restraint is that no send capability
    exists on the port at all -- pin the interface surface the same way
    ADR-0019's canary pins Applicator's."""
    from career_agent.core.interfaces import EmailDraftSink

    public_methods = {
        name for name in vars(EmailDraftSink) if not name.startswith("_")
    }
    assert public_methods == {"create_draft"}
