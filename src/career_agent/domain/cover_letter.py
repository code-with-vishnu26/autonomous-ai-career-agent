"""Deterministic cover-letter assembly from already-gated resume content (ADR-0068).

Phase 50 asks for "generate tailored cover letter." The repository-reality
audit found this cannot reuse ``LLMResumeGenerator`` as-is: that generator
(and the truthfulness gate downstream of it) is built and proven against one
content shape, :class:`~career_agent.domain.models.TailoredContent`
(structured JSON-Resume-like fields, each highlight one atomic
``Statement``) -- not freeform prose. Extending the gate to verify
freeform-paragraph output is a real, separate design problem (how does a
gate atomize and verify sentences inside a paragraph?), not something to
bolt on inside this phase.

Instead, a cover letter here is assembled **deterministically, with zero new
LLM calls and zero new fabrication surface**, entirely out of a
:class:`~career_agent.domain.models.TailoredResume` that has *already*
passed the truthfulness gate (``truthfulness.approved`` is a precondition
this module trusts, the same "gate already ran" trust
``render_tailored_resume`` documents for dates). Nothing here can say
anything the resume itself does not already say -- a direct, conservative
application of the "verified vs. stubbed" capability discipline
(ADR-0066): declare an honest, narrower capability now, rather than guess
at a wider one. Real LLM-authored cover-letter prose, gated by its own
verification scheme, is named future work in ADR-0068, not built here.

Pure, zero-I/O, living in ``domain/`` -- the same precedent as
``render_tailored_resume`` (ADR-0025).
"""

from __future__ import annotations

from pydantic import BaseModel

from .models import Opportunity, TailoredContent

#: How many top highlights (across all tailored work entries, in order) the
#: assembled body paragraph draws from -- bounded so the letter stays a
#: letter, not a re-listing of the entire resume.
_MAX_BODY_HIGHLIGHTS = 3


class TailoredCoverLetter(BaseModel):
    """A deterministically assembled cover letter for one opportunity.

    Carries no :class:`~career_agent.domain.models.TruthfulnessResult` of
    its own -- unlike :class:`~career_agent.domain.models.TailoredResume`,
    it does not need one: every sentence is copied or trivially templated
    from ``TailoredContent`` fields the gate already approved, so there is
    nothing new here for a gate to verify.
    """

    opportunity_id: str
    profile_version: str
    body: str


def assemble_cover_letter(
    content: TailoredContent,
    opportunity: Opportunity,
    *,
    profile_version: str,
    applicant_name: str,
) -> TailoredCoverLetter:
    """Assemble a cover letter body from already-approved ``content``.

    Every sentence traces to ``content.summary`` or one of
    ``content.work[].highlights`` -- copied verbatim, never paraphrased or
    extended, so nothing here can drift from what the truthfulness gate
    already verified for this exact ``content``. The employer name comes
    from ``opportunity.canonical_company`` (ADR-0014's cross-source
    identity) -- no separate ``Company`` lookup is introduced, the same
    "no separate CompanyRepository" precedent ``TieredApplicator`` already
    established.
    """
    highlights: list[str] = []
    for entry in content.work:
        for highlight in entry.highlights:
            highlights.append(highlight)
            if len(highlights) >= _MAX_BODY_HIGHLIGHTS:
                break
        if len(highlights) >= _MAX_BODY_HIGHLIGHTS:
            break

    company_name = opportunity.canonical_company
    paragraphs = [
        f"Dear {company_name} Hiring Team,",
        "",
        f"I am writing to apply for the {opportunity.title} position at "
        f"{company_name}. {content.summary}",
    ]
    if highlights:
        paragraphs.append("")
        paragraphs.append(
            "Relevant to this role, "
            + " ".join(highlight.rstrip(".") + "." for highlight in highlights)
        )
    paragraphs.extend(["", "Sincerely,", applicant_name])

    body = "\n".join(paragraphs).rstrip() + "\n"
    return TailoredCoverLetter(
        opportunity_id=opportunity.id,
        profile_version=profile_version,
        body=body,
    )
