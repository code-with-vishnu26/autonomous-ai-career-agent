"""Phase 57 (ADR-0075): AI Resume Suggestions -- draft, then verify or drop."""

from __future__ import annotations

import pytest

from career_agent.agents.coach.resume_suggestions import (
    CoachAdvisorError,
    generate_resume_suggestions,
)
from career_agent.core.interfaces import ClaimVerdict
from tests._fakes import FakeCareerCoachAdvisor, FakeClaimVerifier


async def test_verified_suggestion_is_returned() -> None:
    advisor = FakeCareerCoachAdvisor(
        '[{"original": "Wrote code.", "suggested": "Built the API.", '
        '"reason": "Stronger verb, matches JD language."}]'
    )
    verifier = FakeClaimVerifier(
        {"Built the API.": ClaimVerdict(verified=True, confidence=0.9)}
    )
    result = await generate_resume_suggestions(
        "Wrote code.", "Looking for an API builder.", advisor=advisor, verifier=verifier
    )
    assert len(result) == 1
    assert result[0].suggested == "Built the API."
    assert result[0].reason == "Stronger verb, matches JD language."


async def test_unverified_suggestion_is_dropped_not_raised() -> None:
    advisor = FakeCareerCoachAdvisor(
        '[{"original": "Wrote code.", "suggested": "Architected a global platform.", '
        '"reason": "Sounds stronger."}]'
    )
    verifier = FakeClaimVerifier(
        {"Architected a global platform.": ClaimVerdict(verified=False, confidence=0.2)}
    )
    result = await generate_resume_suggestions(
        "Wrote code.", "Looking for an architect.", advisor=advisor, verifier=verifier
    )
    assert result == []


async def test_low_confidence_verified_suggestion_is_dropped() -> None:
    advisor = FakeCareerCoachAdvisor(
        '[{"original": "Wrote code.", "suggested": "Built the API.", "reason": "x"}]'
    )
    verifier = FakeClaimVerifier(
        {"Built the API.": ClaimVerdict(verified=True, confidence=0.5)}
    )
    result = await generate_resume_suggestions(
        "Wrote code.", "jd", advisor=advisor, verifier=verifier
    )
    assert result == []


async def test_malformed_advisor_response_raises_not_empty() -> None:
    advisor = FakeCareerCoachAdvisor("not json at all")
    verifier = FakeClaimVerifier({})
    with pytest.raises(CoachAdvisorError):
        await generate_resume_suggestions(
            "resume", "jd", advisor=advisor, verifier=verifier
        )


async def test_advisor_failure_raises_coach_advisor_error() -> None:
    advisor = FakeCareerCoachAdvisor(RuntimeError("network down"))
    verifier = FakeClaimVerifier({})
    with pytest.raises(CoachAdvisorError):
        await generate_resume_suggestions(
            "resume", "jd", advisor=advisor, verifier=verifier
        )
