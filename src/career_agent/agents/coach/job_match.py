"""Job Match Score: how well a resume covers one job description (ADR-0075).

The same coverage number Resume Analysis reports, under the name the
brief's UI mockups use -- kept as its own thin module rather than folded
into ``resume_analyzer`` so the two pages can evolve independently without
one call site's response shape leaking into the other's.
"""

from __future__ import annotations

from pydantic import BaseModel

from career_agent.domain.ats_scoring import MissingKeyword
from career_agent.domain.coach_analysis import MatchedSkill, score_coverage


class JobMatchResult(BaseModel):
    """How well one resume matches one job description."""

    match_score: float  # 0-100
    matched_keywords: list[MatchedSkill]
    missing_keywords: list[MissingKeyword]


def job_match_score(resume_text: str, jd_text: str) -> JobMatchResult:
    """Score ``resume_text`` against ``jd_text``'s curated-taxonomy keywords."""
    coverage = score_coverage(resume_text, jd_text)
    return JobMatchResult(
        match_score=coverage.score,
        matched_keywords=coverage.matched,
        missing_keywords=coverage.missing,
    )
