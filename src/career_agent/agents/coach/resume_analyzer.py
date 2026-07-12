"""Resume Analysis: deterministic ATS-style scan of freeform resume text (ADR-0075).

Combines :mod:`career_agent.domain.coach_analysis`'s three independent
checks (keyword coverage, weak bullets, formatting) into the one response
shape the Career Coach's Resume Analysis page needs. No LLM call, no
fabrication surface -- every field traces to a deterministic, explainable
check.
"""

from __future__ import annotations

from pydantic import BaseModel

from career_agent.domain.ats_scoring import MissingKeyword
from career_agent.domain.coach_analysis import (
    BulletIssue,
    FormattingIssue,
    MatchedSkill,
    find_formatting_issues,
    find_weak_bullets,
    score_coverage,
)


class ResumeAnalysis(BaseModel):
    """The full Resume Analysis result for one resume/JD pair."""

    ats_score: float  # 0-100, keyword-coverage based
    matched_keywords: list[MatchedSkill]
    missing_keywords: list[MissingKeyword]
    weak_bullets: list[BulletIssue]
    formatting_issues: list[FormattingIssue]


def analyze_resume(resume_text: str, jd_text: str) -> ResumeAnalysis:
    """Run every deterministic Resume Analysis check against one resume/JD pair."""
    coverage = score_coverage(resume_text, jd_text)
    return ResumeAnalysis(
        ats_score=coverage.score,
        matched_keywords=coverage.matched,
        missing_keywords=coverage.missing,
        weak_bullets=find_weak_bullets(resume_text),
        formatting_issues=find_formatting_issues(resume_text),
    )
