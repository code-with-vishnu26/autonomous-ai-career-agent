"""Phase 7 / ADR-0018: TieredApplicator's confirmation-token binding is the
load-bearing guarantee -- submit() must never reach the ATS adapter unless
the confirmation names the exact preview prepare() issued.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.agents.apply.applicator import SubmissionError, TieredApplicator
from career_agent.core.events import ApplicationFailed, ApplicationSubmitted
from career_agent.domain.models import (
    Application,
    HumanConfirmation,
    Statement,
    SubmittableApplication,
    TailoredContent,
    TailoredResume,
    TruthfulnessResult,
)
from tests._fakes import FakeATSAdapter


def _approved_application(app_id: str = "app-1") -> SubmittableApplication:
    resume = TailoredResume(
        id="resume-1",
        opportunity_id="opp-1",
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
        id=app_id, opportunity_id="opp-1", resume=resume, status="pending"
    )
    return SubmittableApplication(application=app)


def _confirmation(preview_token: str) -> HumanConfirmation:
    return HumanConfirmation(
        preview_token=preview_token,
        confirmed_by="test-user",
        confirmed_at=datetime.now(UTC),
    )


async def test_prepare_performs_no_submission() -> None:
    adapter = FakeATSAdapter()
    applicator = TieredApplicator(adapter)
    await applicator.prepare(_approved_application())
    assert adapter.calls == []


async def test_matching_confirmation_submits_through_the_adapter() -> None:
    adapter = FakeATSAdapter()
    applicator = TieredApplicator(adapter)
    preview = await applicator.prepare(_approved_application())
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationSubmitted)
    assert len(adapter.calls) == 1


async def test_mismatched_confirmation_token_is_refused_before_the_adapter() -> None:
    """The load-bearing test: a confirmation naming a different token must
    never let the adapter be reached at all -- not "reached but rejected"."""
    adapter = FakeATSAdapter()
    applicator = TieredApplicator(adapter)
    preview = await applicator.prepare(_approved_application())
    with pytest.raises(ValueError, match="confirmation"):
        await applicator.submit(preview, _confirmation("a-different-token"))
    assert adapter.calls == []


async def test_confirming_an_unknown_preview_token_is_refused() -> None:
    adapter = FakeATSAdapter()
    applicator = TieredApplicator(adapter)
    forged_preview = (await applicator.prepare(_approved_application())).model_copy(
        update={"preview_token": "never-issued"}
    )
    with pytest.raises(ValueError, match="unknown"):
        await applicator.submit(forged_preview, _confirmation("never-issued"))
    assert adapter.calls == []


async def test_a_confirmed_token_cannot_be_replayed() -> None:
    """One-shot: the token is consumed on first submit, so replaying the same
    (preview, confirmation) pair a second time must not submit again."""
    adapter = FakeATSAdapter()
    applicator = TieredApplicator(adapter)
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
        submit_outcomes={
            "app-1": SubmissionError("duplicate_submission", "already applied")
        }
    )
    applicator = TieredApplicator(adapter)
    preview = await applicator.prepare(_approved_application())
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationFailed)
    assert event.error_category == "duplicate_submission"
    assert event.tier_attempted == "ats_api"
    # the failure still consumed the token -- a retry must call prepare() again
    assert len(adapter.calls) == 1


async def test_prepare_issues_a_fresh_token_each_call() -> None:
    adapter = FakeATSAdapter()
    applicator = TieredApplicator(adapter)
    app = _approved_application()
    first = await applicator.prepare(app)
    second = await applicator.prepare(app)
    assert first.preview_token != second.preview_token
