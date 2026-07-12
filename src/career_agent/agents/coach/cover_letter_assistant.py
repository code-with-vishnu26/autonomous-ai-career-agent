"""Cover Letter Assistant: LLM rewrite of an already-assembled letter, verified.

Phase 57, ADR-0075.

Takes the ``body`` of a :class:`~career_agent.domain.cover_letter.TailoredCoverLetter`
that :func:`~career_agent.domain.cover_letter.assemble_cover_letter` already
built deterministically from gated resume content, and transforms it --
rewrite, shorten, more formal, or more technical -- via the Career Coach
advisor. The transformed text is verified against the *original* body by
the same :class:`~career_agent.core.interfaces.ClaimVerifier` the
truthfulness gate uses before it is ever returned, so a transformation
that quietly adds a new claim not in the original is dropped, not
surfaced -- fail closed, the same discipline
:mod:`career_agent.agents.coach.resume_suggestions` uses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from career_agent.core.interfaces import CareerCoachAdvisor, ClaimVerifier

_CONFIDENCE_THRESHOLD = 0.7

CoverLetterMode = Literal["rewrite", "shorten", "more_formal", "more_technical"]

_MODE_INSTRUCTIONS: dict[CoverLetterMode, str] = {
    "rewrite": (
        "Rewrite this cover letter with fresher phrasing, keeping every fact as-is."
    ),
    "shorten": (
        "Shorten this cover letter to roughly half its length, keeping every "
        "fact as-is."
    ),
    "more_formal": (
        "Rewrite this cover letter in a more formal tone, keeping every fact as-is."
    ),
    "more_technical": (
        "Rewrite this cover letter to emphasize technical language and "
        "specifics already present in the text, keeping every fact as-is."
    ),
}

_TRANSFORM_PROMPT = """\
You are a cover-letter editing assistant. {instruction}

CRITICAL RULE: Do not add any fact, employer, number, or claim that is not \
already present in the letter below. Only rephrase, reorganize, or trim.

Cover letter:
{body}

Respond with ONLY the rewritten cover letter text, no other commentary.
"""


class CoverLetterTransformResult(BaseModel):
    """One verified, advisory rewrite of a cover letter body."""

    mode: str
    original: str
    transformed: str
    confidence: float


class CoverLetterTransformRejectedError(Exception):
    """The advisor's rewrite could not be verified against the original -- dropped."""


class CoachAdvisorError(Exception):
    """The advisor call itself failed."""


async def transform_cover_letter(
    body: str,
    mode: CoverLetterMode,
    *,
    advisor: CareerCoachAdvisor,
    verifier: ClaimVerifier,
) -> CoverLetterTransformResult:
    """Transform ``body`` per ``mode``, verified against the original before returning.

    Raises :class:`CoachAdvisorError` on an advisor call failure, and
    :class:`CoverLetterTransformRejectedError` (fail closed, never a
    silent fallback to the unmodified text) if the verifier cannot confirm
    the rewrite is entailed by the original.
    """
    prompt = _TRANSFORM_PROMPT.format(instruction=_MODE_INSTRUCTIONS[mode], body=body)
    try:
        transformed = (await advisor.draft_text(prompt, max_tokens=1200)).strip()
    except Exception as exc:  # noqa: BLE001 -- any failure here must fail closed
        raise CoachAdvisorError(f"Cover letter transformation failed: {exc}") from exc

    if not transformed:
        raise CoverLetterTransformRejectedError("The advisor returned no text.")

    verdict = await verifier.verify_claim(transformed, body)
    if not (verdict.verified and verdict.confidence >= _CONFIDENCE_THRESHOLD):
        raise CoverLetterTransformRejectedError(
            "The rewritten letter could not be verified against the original "
            f"(verified={verdict.verified}, confidence={verdict.confidence:.2f}) "
            "-- it may introduce a claim the original letter does not support."
        )
    return CoverLetterTransformResult(
        mode=mode, original=body, transformed=transformed, confidence=verdict.confidence
    )
