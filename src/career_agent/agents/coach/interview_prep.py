"""Interview Preparation: JD-grounded practice questions and STAR guidance (ADR-0075).

Unlike Resume Suggestions and the Cover Letter Assistant, this feature's
output is never a claim about the candidate -- it is questions to expect
and generic guidance on how to structure an answer (STAR: Situation, Task,
Action, Result). There is no achievement to fabricate, so no
:class:`~career_agent.core.interfaces.ClaimVerifier` call is needed here;
the fabrication risk this module actually carries is a question that
implies something about the *company* the job description doesn't
support, which is why every question is required to explain which part of
the job description prompted it -- "company-specific" here means
"specific to what this job description says," never invented outside
knowledge about the employer (Company Research, which has no real data
source in this codebase, is explicitly deferred -- see ADR-0075).
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from career_agent.core.interfaces import CareerCoachAdvisor

_PREP_PROMPT = """\
You are an interview coach. Given the job description below, produce \
interview preparation material grounded ONLY in what this job description \
says -- do not invent facts about the company that are not stated here.

Job description:
{jd_text}

Respond with ONLY a JSON object, no other text, shaped exactly like:
{{
  "technical_questions": [{{"question": "...", "why": "..."}}],
  "behavioral_questions": [{{"question": "...", "why": "..."}}],
  "role_specific_questions": [{{"question": "...", "why": "..."}}],
  "star_guidance": "one paragraph of guidance on structuring answers with STAR"
}}
Produce up to 5 items in each question list. Every "why" must cite the \
specific part of the job description that prompted the question.
"""


class PrepQuestion(BaseModel):
    """One interview question and why it was chosen."""

    question: str
    why: str


class InterviewPrepResult(BaseModel):
    """The full Interview Preparation result for one job description."""

    technical_questions: list[PrepQuestion]
    behavioral_questions: list[PrepQuestion]
    role_specific_questions: list[PrepQuestion]
    star_guidance: str


class CoachAdvisorError(Exception):
    """The advisor call failed or returned an unparseable response."""


def _parse_questions(raw: object) -> list[PrepQuestion]:
    if not isinstance(raw, list):
        return []
    return [
        PrepQuestion(
            question=str(item.get("question", "")), why=str(item.get("why", ""))
        )
        for item in raw
        if isinstance(item, dict) and item.get("question")
    ]


async def generate_interview_prep(
    jd_text: str, *, advisor: CareerCoachAdvisor
) -> InterviewPrepResult:
    """Draft JD-grounded interview questions plus general STAR guidance.

    Raises :class:`CoachAdvisorError` on a call failure or an unparseable
    response -- an empty result must never be confused with "nothing to
    ask about this role."
    """
    prompt = _PREP_PROMPT.format(jd_text=jd_text)
    try:
        text = await advisor.draft_text(prompt, max_tokens=2000)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError(f"no JSON object found in advisor response: {text!r}")
        payload = json.loads(text[start : end + 1])
    except Exception as exc:  # noqa: BLE001 -- any failure here must fail closed
        raise CoachAdvisorError(f"Interview prep drafting failed: {exc}") from exc

    return InterviewPrepResult(
        technical_questions=_parse_questions(payload.get("technical_questions")),
        behavioral_questions=_parse_questions(payload.get("behavioral_questions")),
        role_specific_questions=_parse_questions(payload.get("role_specific_questions")),
        star_guidance=str(payload.get("star_guidance", "")),
    )
