"""Phase 57 (ADR-0075): Interview Preparation -- JD-grounded, no claim gate."""

from __future__ import annotations

import pytest

from career_agent.agents.coach.interview_prep import (
    CoachAdvisorError,
    generate_interview_prep,
)
from tests._fakes import FakeCareerCoachAdvisor

_VALID_RESPONSE = """\
{
  "technical_questions": [
    {"question": "Explain your Python experience.", "why": "JD requires Python."}
  ],
  "behavioral_questions": [
    {"question": "Tell me about a conflict.", "why": "General behavioral question."}
  ],
  "role_specific_questions": [],
  "star_guidance": "Use Situation, Task, Action, Result."
}
"""


async def test_parses_a_well_formed_response() -> None:
    advisor = FakeCareerCoachAdvisor(_VALID_RESPONSE)
    result = await generate_interview_prep("Python developer needed.", advisor=advisor)
    assert result.technical_questions[0].question == "Explain your Python experience."
    assert result.star_guidance == "Use Situation, Task, Action, Result."
    assert result.role_specific_questions == []


async def test_malformed_response_raises_not_empty() -> None:
    advisor = FakeCareerCoachAdvisor("no json here")
    with pytest.raises(CoachAdvisorError):
        await generate_interview_prep("jd", advisor=advisor)


async def test_advisor_failure_raises_coach_advisor_error() -> None:
    advisor = FakeCareerCoachAdvisor(RuntimeError("network down"))
    with pytest.raises(CoachAdvisorError):
        await generate_interview_prep("jd", advisor=advisor)
