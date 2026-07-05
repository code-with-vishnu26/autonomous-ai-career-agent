"""Phase 17 / ADR-0041: the two pre-scheduling gates + the bounded auto pass."""

from __future__ import annotations

import inspect

import pytest

from career_agent.agents.apply.pipeline import (
    StaleProfileError,
    SubmissionPipeline,
)
from career_agent.cli import run_auto_command
from career_agent.integrations.sent_mail import (
    SentCheckUnavailableError,
    SentMailChecker,
    confirm_email_sent,
)

# --- Gate (a): profile-staleness re-verification ---------------------------


class _RecordingApplicator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def prepare(self, submittable):
        self.calls.append("prepare")
        raise AssertionError("prepare must never be reached in these tests")

    async def submit(self, preview, confirmation):
        self.calls.append("submit")


def _build_submittable():
    from career_agent.domain.models import (
        Application,
        BasicsSection,
        LegalStatusSection,
        Statement,
        SubmittableApplication,
        TailoredContent,
        TailoredResume,
        TruthfulnessResult,
    )

    resume = TailoredResume(
        id="r1",
        opportunity_id="opp-1",
        profile_version="profile-vOLD",
        content=TailoredContent(summary="Engineer."),
        truthfulness=TruthfulnessResult(
            profile_version="profile-vOLD",
            approved=True,
            statements=[
                Statement(text="x", evidence=None, confidence=1, verified=True)
            ],
            prompt_version="p1",
        ),
    )
    return SubmittableApplication(
        application=Application(
            id="app-1",
            opportunity_id="opp-1",
            resume=resume,
            applicant=BasicsSection(name="Ada", email="ada@example.com"),
            legal_status=LegalStatusSection(),
            status="pending",
        )
    )


async def test_stale_profile_refuses_before_prepare_ever_runs():
    """The gate fires BEFORE prepare(): a stale application never even
    produces a preview a human could mistakenly confirm."""
    applicator = _RecordingApplicator()
    pipeline = SubmissionPipeline(
        applicator,
        lambda preview: pytest.fail("confirm must never be reached"),
        current_profile_version="profile-vNEW",
    )
    with pytest.raises(StaleProfileError, match="re-run tailoring"):
        await pipeline.run(_build_submittable())
    assert applicator.calls == []  # the 7a proof shape: nothing ever fired


async def test_matching_profile_version_proceeds():
    class _Applicator:
        async def prepare(self, submittable):
            from career_agent.domain.models import SubmissionPreview

            return SubmissionPreview(
                application_id="app-1",
                tier="ats_api",
                target="https://example.invalid",
                rendered_content="x",
                preview_token="t",
            )

        async def submit(self, preview, confirmation):
            raise AssertionError("declined confirmation never submits")

    pipeline = SubmissionPipeline(
        _Applicator(), lambda preview: None, current_profile_version="profile-vOLD"
    )
    assert await pipeline.run(_build_submittable()) is None  # clean decline


async def test_no_version_supplied_keeps_existing_behavior():
    pipeline = SubmissionPipeline(
        _RecordingApplicator.__new__(_RecordingApplicator),
        lambda preview: None,
    )
    # No current_profile_version -> no staleness gate (backward compatible);
    # this still fails at prepare() -- proving the gate itself was skipped.
    pipeline._applicator = _RecordingApplicator()
    with pytest.raises(AssertionError, match="never be reached"):
        await pipeline.run(_build_submittable())


# --- Gate (b): email send-confirmation ------------------------------------


class _FoundChecker:
    async def was_sent(self, *, to: str, subject: str) -> bool:
        return True


class _MissingChecker:
    async def was_sent(self, *, to: str, subject: str) -> bool:
        return False


class _BrokenChecker:
    async def was_sent(self, *, to: str, subject: str) -> bool:
        raise ConnectionError("gmail unreachable")


async def test_send_confirmation_positive_observation_only():
    assert await confirm_email_sent(_FoundChecker(), to="a@b.c", subject="S")
    assert not await confirm_email_sent(_MissingChecker(), to="a@b.c", subject="S")


async def test_checker_failure_is_an_unknown_never_a_boolean():
    """'We couldn't look' must never advance an application (false yes)
    nor read as 'not sent' (false no) -- it raises, typed."""
    with pytest.raises(SentCheckUnavailableError, match="could not check"):
        await confirm_email_sent(_BrokenChecker(), to="a@b.c", subject="S")


def test_sent_mail_checker_port_has_no_send_capability():
    """Same interface-level restraint as EmailDraftSink: observation only."""
    members = [name for name in dir(SentMailChecker) if not name.startswith("_")]
    assert members == ["was_sent"]


# --- The bounded auto pass: structurally cannot confirm or submit ----------


def test_auto_command_structurally_cannot_confirm_or_submit():
    """The 1d proof shape applied to scheduling: run_auto_command takes no
    input function and its code references no confirmation or submission
    machinery at all -- there is no channel through which an automated
    pass could ever submit."""
    signature = inspect.signature(run_auto_command)
    assert "input_fn" not in signature.parameters
    code_names = set(run_auto_command.__code__.co_names)
    for forbidden in (
        "confirm_submission",
        "SubmissionPipeline",
        "HumanConfirmation",
        "submit",
    ):
        assert forbidden not in code_names
