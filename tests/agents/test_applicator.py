"""Phase 7 / ADR-0018, ADR-0019: TieredApplicator's confirmation-token binding
and ats_kind resolution -- submit() must never reach the ATS adapter unless
the confirmation names the exact preview prepare() issued, and prepare()
must never guess an adapter for an opportunity it can't resolve.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.agents.apply.applicator import (
    NoApplicableAdapterError,
    SubmissionError,
    TieredApplicator,
)
from career_agent.core.events import ApplicationFailed, ApplicationSubmitted
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


def _opportunity(opportunity_id: str, source_url: str) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="acme.com",
        title="Software Engineer",
        source="ats_api",
        source_url=source_url,
        provenance=Provenance(
            method="structured_api",
            reference=source_url,
            extraction_confidence=1.0,
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def _repo_with(opportunity: Opportunity) -> InMemoryOpportunityRepository:
    repo = InMemoryOpportunityRepository()
    await repo.add(opportunity)
    return repo


def _approved_application(
    app_id: str = "app-1", opportunity_id: str = "opp-1"
) -> SubmittableApplication:
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
        id=app_id,
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


async def _greenhouse_applicator() -> tuple[TieredApplicator, FakeATSAdapter]:
    adapter = FakeATSAdapter(ats_kind="greenhouse")
    repo = await _repo_with(
        _opportunity("opp-1", "https://boards.greenhouse.io/acme/jobs/12345")
    )
    return TieredApplicator({"greenhouse": adapter}, repo), adapter


# ---------------------------------------------------------------------------
# ats_kind resolution (ADR-0019)
# ---------------------------------------------------------------------------


async def test_prepare_resolves_the_registered_adapter_from_source_url() -> None:
    applicator, adapter = await _greenhouse_applicator()
    preview = await applicator.prepare(_approved_application())
    assert preview.target == "greenhouse"
    assert adapter.calls == []  # prepare() alone never reaches the adapter


async def test_prepare_raises_when_the_opportunity_is_unresolvable() -> None:
    adapter = FakeATSAdapter(ats_kind="greenhouse")
    repo = InMemoryOpportunityRepository()  # empty -- no such opportunity
    applicator = TieredApplicator({"greenhouse": adapter}, repo)
    with pytest.raises(NoApplicableAdapterError, match="not found"):
        await applicator.prepare(_approved_application())


async def test_prepare_raises_when_the_url_matches_no_known_ats_pattern() -> None:
    adapter = FakeATSAdapter(ats_kind="greenhouse")
    repo = await _repo_with(
        _opportunity("opp-1", "https://example.com/careers/some-job")
    )
    applicator = TieredApplicator({"greenhouse": adapter}, repo)
    with pytest.raises(NoApplicableAdapterError):
        await applicator.prepare(_approved_application())


async def test_prepare_raises_when_the_matched_ats_kind_has_no_registered_adapter() -> (
    None
):
    """The URL resolves to a real ats_kind (lever), but this Applicator only
    has a greenhouse adapter registered -- must fail explicitly, not guess."""
    adapter = FakeATSAdapter(ats_kind="greenhouse")
    repo = await _repo_with(
        _opportunity("opp-1", "https://jobs.lever.co/acme/abc-123")
    )
    applicator = TieredApplicator({"greenhouse": adapter}, repo)
    with pytest.raises(NoApplicableAdapterError, match="no Tier 1 adapter"):
        await applicator.prepare(_approved_application())


# ---------------------------------------------------------------------------
# Confirmation-token binding (ADR-0018)
# ---------------------------------------------------------------------------


async def test_prepare_performs_no_submission() -> None:
    applicator, adapter = await _greenhouse_applicator()
    await applicator.prepare(_approved_application())
    assert adapter.calls == []


async def test_matching_confirmation_submits_through_the_resolved_adapter() -> None:
    applicator, adapter = await _greenhouse_applicator()
    preview = await applicator.prepare(_approved_application())
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationSubmitted)
    assert len(adapter.calls) == 1


async def test_mismatched_confirmation_token_is_refused_before_the_adapter() -> None:
    """The load-bearing test: a confirmation naming a different token must
    never let the adapter be reached at all -- not "reached but rejected"."""
    applicator, adapter = await _greenhouse_applicator()
    preview = await applicator.prepare(_approved_application())
    with pytest.raises(ValueError, match="confirmation"):
        await applicator.submit(preview, _confirmation("a-different-token"))
    assert adapter.calls == []


async def test_confirming_an_unknown_preview_token_is_refused() -> None:
    applicator, adapter = await _greenhouse_applicator()
    forged_preview = (await applicator.prepare(_approved_application())).model_copy(
        update={"preview_token": "never-issued"}
    )
    with pytest.raises(ValueError, match="unknown"):
        await applicator.submit(forged_preview, _confirmation("never-issued"))
    assert adapter.calls == []


async def test_a_confirmed_token_cannot_be_replayed() -> None:
    """One-shot: the token is consumed on first submit, so replaying the same
    (preview, confirmation) pair a second time must not submit again."""
    applicator, adapter = await _greenhouse_applicator()
    preview = await applicator.prepare(_approved_application())
    confirmation = _confirmation(preview.preview_token)
    await applicator.submit(preview, confirmation)
    assert len(adapter.calls) == 1
    with pytest.raises(ValueError, match="unknown"):
        await applicator.submit(preview, confirmation)
    assert len(adapter.calls) == 1  # still one -- the replay never reached it


async def test_a_real_ats_failure_becomes_applicationfailed_not_a_crash() -> None:
    """Modeling error/partial-failure responses, not just the happy path --
    a duplicate-submission response from a real ATS is a legitimate outcome,
    distinct from a confirmation/token misuse error."""
    adapter = FakeATSAdapter(
        ats_kind="greenhouse",
        submit_outcomes={
            "app-1": SubmissionError("duplicate_submission", "already applied")
        },
    )
    repo = await _repo_with(
        _opportunity("opp-1", "https://boards.greenhouse.io/acme/jobs/12345")
    )
    applicator = TieredApplicator({"greenhouse": adapter}, repo)
    preview = await applicator.prepare(_approved_application())
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationFailed)
    assert event.error_category == "duplicate_submission"
    assert event.tier_attempted == "ats_api"
    # the failure still consumed the token -- a retry must call prepare() again
    assert len(adapter.calls) == 1


async def test_prepare_issues_a_fresh_token_each_call() -> None:
    applicator, _adapter = await _greenhouse_applicator()
    app = _approved_application()
    first = await applicator.prepare(app)
    second = await applicator.prepare(app)
    assert first.preview_token != second.preview_token
