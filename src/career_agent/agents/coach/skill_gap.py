"""Skill Gap Analysis: missing JD skills ranked by a documented heuristic (ADR-0075).

"Learning priority" is not a learned ranking model -- there is no outcome
data (interviews, offers) anywhere in this codebase to train one on (see
ADR-0075's reasoning for why Weekly Career Report is deferred for exactly
that gap). Priority here is a fixed, explainable heuristic: hard skills
before soft skills, then by how early each keyword first appears in the
job description -- each entry's ``reason`` says exactly that, never more.
"""

from __future__ import annotations

from pydantic import BaseModel

from career_agent.domain.coach_analysis import learning_priority, score_coverage


class PrioritizedGap(BaseModel):
    """One missing skill plus the explanation for its ranking."""

    keyword: str
    kind: str
    reason: str


class SkillGapReport(BaseModel):
    """The full Skill Gap Analysis result for one resume/JD pair."""

    qualifies_percent: float  # 0-100, same coverage score as Job Match
    missing_skills: list[PrioritizedGap]  # ranked, highest priority first


def skill_gap_report(resume_text: str, jd_text: str) -> SkillGapReport:
    """Rank ``jd_text``'s missing (vs. ``resume_text``) skills by learning priority."""
    coverage = score_coverage(resume_text, jd_text)
    ranked = learning_priority(coverage.missing, jd_text)
    gaps = [
        PrioritizedGap(
            keyword=item.keyword,
            kind=item.kind,
            reason=(
                f"{'A hard' if item.kind == 'hard' else 'A soft'} skill "
                "requirement" + (
                    " that appears early in the job description."
                    if jd_text.lower().find(item.keyword.lower()) != -1
                    and jd_text.lower().find(item.keyword.lower())
                    < len(jd_text) / 2
                    else " mentioned in the job description."
                )
            ),
        )
        for item in ranked
    ]
    return SkillGapReport(qualifies_percent=coverage.score, missing_skills=gaps)
