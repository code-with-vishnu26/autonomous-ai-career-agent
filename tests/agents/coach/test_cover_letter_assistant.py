"""Phase 57 (ADR-0075): Cover Letter Assistant -- transform, then verify or reject."""

from __future__ import annotations

import pytest

from career_agent.agents.coach.cover_letter_assistant import (
    CoachAdvisorError,
    CoverLetterTransformRejectedError,
    transform_cover_letter,
)
from career_agent.core.interfaces import ClaimVerdict
from tests._fakes import FakeCareerCoachAdvisor, FakeClaimVerifier


async def test_verified_transform_is_returned() -> None:
    advisor = FakeCareerCoachAdvisor("A shorter, formal letter.")
    verifier = FakeClaimVerifier(
        {"A shorter, formal letter.": ClaimVerdict(verified=True, confidence=0.85)}
    )
    result = await transform_cover_letter(
        "Dear team, I am excited to apply.",
        "shorten",
        advisor=advisor,
        verifier=verifier,
    )
    assert result.transformed == "A shorter, formal letter."
    assert result.mode == "shorten"


async def test_unverified_transform_is_rejected_not_silently_returned() -> None:
    advisor = FakeCareerCoachAdvisor("I previously won an award for this.")
    verifier = FakeClaimVerifier(
        {
            "I previously won an award for this.": ClaimVerdict(
                verified=False, confidence=0.1
            )
        }
    )
    with pytest.raises(CoverLetterTransformRejectedError):
        await transform_cover_letter(
            "Dear team, I am excited to apply.",
            "more_formal",
            advisor=advisor,
            verifier=verifier,
        )


async def test_empty_advisor_response_is_rejected() -> None:
    advisor = FakeCareerCoachAdvisor("   ")
    verifier = FakeClaimVerifier({})
    with pytest.raises(CoverLetterTransformRejectedError):
        await transform_cover_letter(
            "Dear team.", "rewrite", advisor=advisor, verifier=verifier
        )


async def test_advisor_failure_raises_coach_advisor_error() -> None:
    advisor = FakeCareerCoachAdvisor(RuntimeError("network down"))
    verifier = FakeClaimVerifier({})
    with pytest.raises(CoachAdvisorError):
        await transform_cover_letter(
            "Dear team.", "more_technical", advisor=advisor, verifier=verifier
        )
