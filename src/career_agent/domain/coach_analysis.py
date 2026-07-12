"""Deterministic resume-vs-job-description analysis for the Career Coach (ADR-0075).

A distinct, simpler pipeline from :mod:`career_agent.domain.ats_scoring`:
``score_resume`` there scores an already-tailored, structured
``TailoredContent`` against a full ``MasterProfile``'s own sections (contact,
education, contextual-vs-skills-only credit, stuffing detection). The
Career Coach instead scores arbitrary freeform resume text -- pasted or
uploaded, no structured sections, no profile -- against a job description,
for a much lighter "how do I look against this JD" check that works before
a resume has ever been tailored through the real pipeline.

Reuses :func:`~career_agent.domain.ats_scoring.extract_jd_keywords` and the
same curated taxonomy, so the two pipelines never disagree about what a
"hard"/"soft" skill is. Keyword occurrence matching here is a local,
simpler word-boundary check (no stuffing cap, no contextual/skills-only
split -- freeform text has no section structure to distinguish) rather than
reusing ``score_resume``'s private matching helpers, which are shaped for
that different, structured input.

Every function here is a pure, deterministic heuristic -- explicitly
documented as such wherever the result could be mistaken for a model
judgment (Phase 57's "explain why each suggestion is made" principle).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from .ats_scoring import MissingKeyword, extract_jd_keywords


def _normalize(text: str) -> str:
    lowered = text.lower().replace("-", " ").replace("/", " ")
    lowered = re.sub(r"[^\w\s.+#]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _contains_keyword(keyword: str, text: str) -> bool:
    escaped = re.escape(_normalize(keyword))
    pattern = re.compile(rf"(?<!\w){escaped}s?(?!\w)", re.IGNORECASE)
    return pattern.search(_normalize(text)) is not None


class MatchedSkill(BaseModel):
    """One JD-required keyword found in the resume text."""

    keyword: str
    kind: Literal["hard", "soft"]


class CoverageResult(BaseModel):
    """How much of a JD's required (taxonomy) vocabulary a resume text covers.

    ``score`` is the same weighting formula as ``ats_scoring``'s coverage
    sub-score (hard skills 2x, soft skills 1x) -- but computed over
    freeform text with no contextual/stuffing adjustments, so it is a
    lighter, advisory number, not a replacement for the real ATS gate.
    """

    score: float  # 0-100
    matched: list[MatchedSkill]
    missing: list[MissingKeyword]  # hard-first (ats_scoring's own ranking)


def score_coverage(resume_text: str, jd_text: str) -> CoverageResult:
    """Score ``resume_text`` against ``jd_text``'s curated-taxonomy keywords."""
    required = extract_jd_keywords(jd_text)
    matched: list[MatchedSkill] = []
    missing: list[MissingKeyword] = []
    earned = 0.0
    possible = 0.0
    for keyword in required:
        possible += keyword.weight
        if _contains_keyword(keyword.keyword, resume_text):
            earned += keyword.weight
            matched.append(MatchedSkill(keyword=keyword.keyword, kind=keyword.kind))
        else:
            missing.append(keyword)
    score = 100.0 if possible == 0 else (earned / possible) * 100.0
    return CoverageResult(score=score, matched=matched, missing=missing)


#: A curated, fixed list of strong resume action verbs -- a code-reviewed
#: word list, not a model judgment, in the same spirit as
#: ``skills_taxonomy.py``'s curated skill lists.
_ACTION_VERBS = frozenset(
    {
        "led", "built", "designed", "architected", "launched", "shipped",
        "reduced", "increased", "improved", "optimized", "automated",
        "implemented", "developed", "created", "drove", "delivered",
        "managed", "scaled", "migrated", "refactored", "mentored",
        "negotiated", "founded", "spearheaded", "streamlined", "cut",
        "grew", "saved", "accelerated", "resolved", "engineered",
    }
)

_METRIC_PATTERN = re.compile(r"\d")


class BulletIssue(BaseModel):
    """One resume line flagged by the weak-bullet heuristic, with its reason."""

    text: str
    reason: str


def find_weak_bullets(resume_text: str) -> list[BulletIssue]:
    """Flag lines that don't open with a strong action verb or carry no metric.

    A fixed, deterministic heuristic -- not a model judgment -- so every
    flag is reproducible and its reason is exactly what was checked, never
    a black-box score. Blank lines and very short lines (section headers,
    likely) are skipped.
    """
    issues: list[BulletIssue] = []
    for raw_line in resume_text.splitlines():
        line = raw_line.strip().lstrip("-•*").strip()
        if len(line) < 15:
            continue
        first_word = re.match(r"[A-Za-z]+", line)
        opens_with_action_verb = (
            first_word is not None and first_word.group(0).lower() in _ACTION_VERBS
        )
        has_metric = bool(_METRIC_PATTERN.search(line))
        if not opens_with_action_verb and not has_metric:
            issues.append(
                BulletIssue(
                    text=line,
                    reason=(
                        "Doesn't open with a recognized strong action verb "
                        "and has no number/metric -- consider starting with "
                        "one (e.g. 'Led', 'Reduced', 'Built') and quantifying "
                        "the outcome if you can do so truthfully."
                    ),
                )
            )
        elif not opens_with_action_verb:
            issues.append(
                BulletIssue(
                    text=line,
                    reason=(
                        "Doesn't open with a recognized strong action verb -- "
                        "consider starting with one (e.g. 'Led', 'Reduced', "
                        "'Built')."
                    ),
                )
            )
        elif not has_metric:
            issues.append(
                BulletIssue(
                    text=line,
                    reason=(
                        "No number/metric found -- a quantified outcome "
                        "reads stronger, if you can add one truthfully."
                    ),
                )
            )
    return issues


class FormattingIssue(BaseModel):
    """One deterministic, structural formatting problem, with its reason."""

    reason: str


#: Lines longer than this are flagged as likely to wrap badly / read as a
#: dense paragraph rather than a scannable bullet.
_MAX_LINE_LENGTH = 300


def find_formatting_issues(resume_text: str) -> list[FormattingIssue]:
    """Flag deterministic, structural formatting problems in raw resume text.

    Every check here is a plain string/structural test -- no model
    judgment -- so results are exact and reproducible.
    """
    issues: list[FormattingIssue] = []
    if not resume_text.strip():
        issues.append(FormattingIssue(reason="Resume text is empty."))
        return issues
    if "\t" in resume_text:
        issues.append(
            FormattingIssue(
                reason=(
                    "Contains tab characters -- these often render "
                    "inconsistently across ATS parsers; use spaces instead."
                )
            )
        )
    if not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", resume_text):
        issues.append(
            FormattingIssue(
                reason=(
                    "No email address detected -- ATS parsers rely on "
                    "this to file contact info."
                )
            )
        )
    long_lines = [
        line for line in resume_text.splitlines() if len(line) > _MAX_LINE_LENGTH
    ]
    if long_lines:
        issues.append(
            FormattingIssue(
                reason=(
                    f"{len(long_lines)} line(s) longer than {_MAX_LINE_LENGTH} "
                    "characters -- likely to wrap badly or read as a dense "
                    "paragraph rather than a scannable bullet."
                )
            )
        )
    return issues


def learning_priority(
    missing: list[MissingKeyword], jd_text: str
) -> list[MissingKeyword]:
    """Rank missing keywords: hard skills first, then by first appearance in the JD.

    A documented, deterministic heuristic -- not a learned ranking model.
    Each entry is explainable ("a hard requirement" and/or "mentioned early
    in the job description"), matching Phase 57's "explain why" principle.
    Earlier JD mentions are treated as higher-priority on the (unverified
    but common) assumption that job descriptions list their most important
    requirements first.
    """
    normalized_jd = _normalize(jd_text)

    def _first_index(keyword: str) -> int:
        match = re.search(re.escape(_normalize(keyword)), normalized_jd)
        return match.start() if match else len(normalized_jd)

    return sorted(missing, key=lambda item: (-item.weight, _first_index(item.keyword)))
