"""AI Resume Suggestions: LLM-drafted bullet rewordings, verified before surfacing.

Phase 57, ADR-0075.

Directly implements Phase 57's four AI principles for this one feature:

- **Never fabricate achievements**: the advisor is only ever asked to
  *reword* an existing bullet (stronger verb, JD-aligned phrasing) --
  never to invent a new fact, employer, or number. Even so, every
  suggestion is independently re-verified against the original bullet by
  the *same* :class:`~career_agent.core.interfaces.ClaimVerifier` the
  truthfulness gate uses, exactly the "check the evidence, not the
  claimed intent" discipline ADR-0016 established. A suggestion that adds
  an unsupported claim is dropped, not surfaced -- fail closed.
- **Suggestions must be advisory only**: this module has no method that
  writes anything back to a résumé or profile. It returns a list; nothing
  more.
- **Users explicitly accept any changes before they're applied**: there
  is no "apply" channel here at all -- the caller (frontend) presents
  accept/reject as a purely local UI action over this read-only list.
- **Explain why each suggestion is made**: every surfaced item carries the
  advisor's own ``reason``.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from career_agent.core.interfaces import CareerCoachAdvisor, ClaimVerifier

_CONFIDENCE_THRESHOLD = 0.7

_SUGGESTION_PROMPT = """\
You are a resume-writing assistant. You will be given a candidate's resume \
text and a job description. Suggest improved rewordings for up to {limit} \
existing bullet points, to better use the job description's language and \
strengthen the verbs.

CRITICAL RULES:
- Only REWORD existing bullets. Never invent a new fact, employer, project, \
number, or outcome that is not already stated in the original bullet.
- Every "suggested" value must be entailed by its "original" value -- if you \
cannot strengthen a bullet without adding a new claim, skip it.

Resume text:
{resume_text}

Job description:
{jd_text}

Respond with ONLY a JSON array, no other text, of objects shaped exactly like:
[{{"original": "...", "suggested": "...", "reason": "..."}}]
"""


class ResumeSuggestion(BaseModel):
    """One verified, advisory bullet rewording."""

    original: str
    suggested: str
    reason: str
    confidence: float


class CoachAdvisorError(Exception):
    """The advisor call failed or returned an unparseable response."""


async def generate_resume_suggestions(
    resume_text: str,
    jd_text: str,
    *,
    advisor: CareerCoachAdvisor,
    verifier: ClaimVerifier,
    max_suggestions: int = 5,
) -> list[ResumeSuggestion]:
    """Draft bullet rewordings, then keep only the ones the verifier confirms.

    Raises :class:`CoachAdvisorError` if the advisor call itself fails or
    returns something that cannot be parsed as the expected JSON shape --
    an empty result must never be confused with "the advisor said there
    was nothing to improve." A suggestion that fails verification is
    silently dropped (not raised): that is the verifier correctly doing
    its job, not a system failure.
    """
    prompt = _SUGGESTION_PROMPT.format(
        limit=max_suggestions, resume_text=resume_text, jd_text=jd_text
    )
    try:
        text = await advisor.draft_text(prompt, max_tokens=1500)
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise ValueError(f"no JSON array found in advisor response: {text!r}")
        raw_items = json.loads(text[start : end + 1])
    except Exception as exc:  # noqa: BLE001 -- any failure here must fail closed
        raise CoachAdvisorError(f"Resume suggestion drafting failed: {exc}") from exc

    verified: list[ResumeSuggestion] = []
    for item in raw_items[:max_suggestions]:
        original = str(item.get("original", "")).strip()
        suggested = str(item.get("suggested", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not original or not suggested:
            continue
        verdict = await verifier.verify_claim(suggested, original)
        if verdict.verified and verdict.confidence >= _CONFIDENCE_THRESHOLD:
            verified.append(
                ResumeSuggestion(
                    original=original,
                    suggested=suggested,
                    reason=reason,
                    confidence=verdict.confidence,
                )
            )
    return verified
