"""Pick the stored resume variant closest to a job description (ADR-0068).

A "resume variant" is one previously *approved* :class:`TailoredContent`
snapshot, kept around under a free-form ``category`` label (e.g.
``"backend"``, ``"data"``) so a later opportunity in the same category can
start from something already close, instead of the generator drafting a
resume from the master profile cold every time.

``select_closest_variant`` is advisory only: it never gates or blocks
anything, and its output is never treated as the resume itself --
:class:`~career_agent.agents.resume.pipeline.ResumeTailoringPipeline` still
runs its full generate -> truthfulness-gate -> ATS-gate pipeline
unconditionally afterwards (ADR-0068). This function only ever *ranks*
already-approved variants; it does not invent or alter any keyword, so it
carries no fabrication risk and needs no gate of its own -- deterministic
keyword overlap, the same taxonomy-based matching
:mod:`career_agent.domain.ats_scoring` already uses for the real gate, not
a new algorithm.
"""

from __future__ import annotations

from pydantic import BaseModel

from .ats_scoring import extract_jd_keywords
from .models import TailoredContent


class ResumeVariant(BaseModel):
    """One stored, previously-approved resume snapshot for a job category."""

    id: str
    category: str
    profile_version: str
    content: TailoredContent
    created_at: str  # ISO-8601; caller-supplied, domain stays clock-free


def _variant_keyword_set(variant: ResumeVariant) -> set[str]:
    normalized = {skill.strip().lower() for skill in variant.content.skills}
    normalized |= {
        highlight.strip().lower()
        for entry in variant.content.work
        for highlight in entry.highlights
    }
    return normalized


def select_closest_variant(
    variants: list[ResumeVariant], jd_text: str
) -> ResumeVariant | None:
    """Return the variant whose skills best overlap ``jd_text``'s keywords.

    Ties (including an all-zero-overlap tie) are broken by first occurrence
    in ``variants``, so the result is deterministic for a given input order.
    Returns ``None`` for an empty ``variants`` list.
    """
    if not variants:
        return None

    jd_keywords = {
        item.keyword.strip().lower() for item in extract_jd_keywords(jd_text)
    }

    def _score(variant: ResumeVariant) -> int:
        variant_terms = _variant_keyword_set(variant)
        return sum(
            1
            for keyword in jd_keywords
            if any(keyword in term for term in variant_terms)
        )

    best = variants[0]
    best_score = _score(best)
    for variant in variants[1:]:
        score = _score(variant)
        if score > best_score:
            best, best_score = variant, score
    return best
