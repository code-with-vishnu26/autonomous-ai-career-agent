"""Deterministic ATS scoring: the hard gate's pure judgment layer (ADR-0034).

Pipeline position (ADR-0034): tailor -> truthfulness gate -> **ATS gate**
-> render/confirm. Everything in this module is a pure function of its
inputs -- no model calls, no model files, no I/O -- so the same resume
against the same job description produces the same score on any machine,
forever, at this code version. That reproducibility is why the pre-brief
rejected spaCy's statistical model for extraction (uninstallable in this
sandbox, but more importly: a gate whose vocabulary depends on a
downloaded model artifact is only deterministic conditional on that
artifact's version) in favor of the curated taxonomy
(:mod:`career_agent.domain.skills_taxonomy`) plus pure-Python matching.

**The gate decision is computed from the deterministic score alone,
period** (matrix case A1, resolved over the standing brief's looser
"raise but never lower" wording -- which is self-contradictory the moment
a raise crosses the threshold). The LLM semantic layer never touches any
number here: its only role, downstream, is pruning false-missing keywords
from the retailor gap report, and only with a quoted phrase this module
verifies verbatim against the resume text
(:func:`verified_semantic_keywords`, case A3 -- plausibility alone is
not evidence).

**Hard format failures override the numeric score** (case A2): ``passed``
is a computed property of :class:`AtsScoreReport` itself --
``total >= threshold and not format_hard_failures`` -- so the override
lives in the type's own derivation, not in caller discipline.

**Anti-stuffing** (cases C1/C2): a keyword's coverage credit never scales
with repetition; occurrences beyond :data:`STUFFING_OCCURRENCE_CAP` add a
stuffing flag instead of score. A keyword matched *only* in the skills
list, with zero contextual occurrence in the summary or any highlight,
earns :data:`SKILLS_ONLY_CREDIT` (half) and flags -- a bare keyword dump
is not the same evidence as a keyword doing real work in a sentence, and
stuffing truthful keywords is still dishonest presentation.

**GENUINE vs SURFACEABLE** (cases B1/B2): a missing keyword with zero
evidence anywhere in the full profile text is GENUINE -- a skill gap, not
a tailoring gap -- and is structurally excluded from the
:class:`AtsGapReport` injected into any retailor prompt: that type has
**no field that can carry a GENUINE gap**, the same
absence-of-the-channel guarantee as ``answer_eeoc_question`` taking no
``MasterProfile`` parameter. The drafter cannot fabricate toward targets
it is never shown; the full truthfulness gate still re-verifies every
retry independently (defense-in-depth, not the only wall).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from .models import MasterProfile, TailoredContent
from .skills_taxonomy import HARD_SKILLS, SOFT_SKILLS

#: Occurrences of one keyword beyond this add flags, never score (case C1).
STUFFING_OCCURRENCE_CAP = 3
#: Coverage credit for a keyword found only in the skills list (case C2).
SKILLS_ONLY_CREDIT = 0.5

_HARD_WEIGHT = 2.0
_SOFT_WEIGHT = 1.0

_COVERAGE_WEIGHT = 0.45
_TITLE_WEIGHT = 0.15
_SECTIONS_WEIGHT = 0.20
_FORMAT_WEIGHT = 0.20

_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or the to "
    "with we you your our their this that will would".split()
)


def _normalize(text: str) -> str:
    lowered = text.lower().replace("-", " ").replace("/", " ")
    lowered = re.sub(r"[^\w\s.+#]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Word-boundary pattern for a normalized keyword, tolerating a trailing s."""
    escaped = re.escape(_normalize(keyword))
    return re.compile(rf"(?<!\w){escaped}s?(?!\w)", re.IGNORECASE)


def _occurrences(keyword: str, text: str) -> int:
    return len(_keyword_pattern(keyword).findall(_normalize(text)))


class MissingKeyword(BaseModel):
    """One JD-required keyword the resume does not cover, ranked by weight."""

    keyword: str
    kind: Literal["hard", "soft"]

    @property
    def weight(self) -> float:
        """Coverage weight: hard skills count double (ADR-0034)."""
        return _HARD_WEIGHT if self.kind == "hard" else _SOFT_WEIGHT


class KeywordMatch(BaseModel):
    """One covered keyword and how honestly it was covered."""

    keyword: str
    kind: Literal["hard", "soft"]
    occurrences: int
    contextual: bool  # appears in summary/highlights, not only the skills list
    credit: float = Field(ge=0.0, le=1.0)


class AtsScoreReport(BaseModel):
    """The deterministic layer's full verdict on one rendered resume.

    ``passed`` is a computed property, not a stored field: the A2 override
    (a hard format failure fails the gate regardless of the numeric score)
    is part of this type's own derivation and cannot be forgotten by a
    caller. Nothing the LLM semantic layer produces feeds any field here
    (case A1).
    """

    total: float
    threshold: float
    keyword_coverage: float  # 0-100
    title_alignment: float  # 0-100
    section_completeness: float  # 0-100
    format_safety: float  # 0-100
    matched: list[KeywordMatch]
    missing_keywords: list[MissingKeyword]  # ranked hard-first
    stuffing_flags: list[str] = Field(default_factory=list)
    format_hard_failures: list[str] = Field(default_factory=list)
    #: JD terms outside the curated taxonomy -- reported for a human eye,
    #: never scored (ADR-0034: heuristic extraction is advisory-only).
    unrecognized_jd_terms: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        """Threshold met AND no hard format failure (the A2 override)."""
        return self.total >= self.threshold and not self.format_hard_failures


class SurfaceableKeyword(BaseModel):
    """A missing keyword the profile genuinely supports, with its evidence."""

    keyword: str
    profile_evidence: str  # the profile's own text that supports surfacing it


class AtsGapReport(BaseModel):
    """What a retailor attempt is allowed to be told about (cases B1/B2).

    Deliberately has **no field for GENUINE gaps** -- keywords with zero
    profile evidence structurally cannot reach the drafter through this
    type, so "retailor to raise the score" has no channel through which to
    become "fabricate to raise the score." GENUINE gaps are reported to
    the *human* (on :class:`AtsScoreBelowThresholdError`), never to the
    component that writes prose.
    """

    surfaceable: list[SurfaceableKeyword]


class SemanticKeywordClaim(BaseModel):
    """One LLM claim that a missing keyword is present under other wording.

    Worthless on its own: :func:`verified_semantic_keywords` only accepts
    a claim whose ``quoted_phrase`` exists verbatim in the resume text
    (case A3). An unverifiable claim is dropped silently from the pruning
    -- never scored, never surfaced as evidence.
    """

    keyword: str
    quoted_phrase: str


class AtsScoreBelowThresholdError(Exception):
    """Typed refusal: retries exhausted (or converged) and still below threshold.

    Carries the full trajectory so the human sees improvement (or its
    absence), and splits what remains missing into GENUINE gaps (skill
    gaps -- fix the profile/skills, not the tailoring) vs
    surfaceable-but-still-insufficient (case B4). ``converged_early`` is
    case B5: a retry that changed nothing stops the loop honestly instead
    of burning attempts on identical drafts.
    """

    def __init__(  # noqa: D107 -- the class docstring covers construction
        self,
        *,
        trajectory: list[AtsScoreReport],
        genuine_gaps: list[str],
        surfaceable_remaining: list[str],
        converged_early: bool,
    ) -> None:
        self.trajectory = trajectory
        self.genuine_gaps = genuine_gaps
        self.surfaceable_remaining = surfaceable_remaining
        self.converged_early = converged_early
        scores = " -> ".join(f"{report.total:.2f}" for report in trajectory)
        final = trajectory[-1]
        parts = [
            f"ATS score below threshold after {len(trajectory)} attempt(s): "
            f"{scores} (threshold {final.threshold:.2f}).",
            f"Breakdown: keywords {final.keyword_coverage:.0f}, title "
            f"{final.title_alignment:.0f}, sections "
            f"{final.section_completeness:.0f}, format "
            f"{final.format_safety:.0f}.",
        ]
        if converged_early:
            parts.append(
                "Stopped early: no further truthful improvement available "
                "(retailoring converged)."
            )
        if genuine_gaps:
            parts.append(
                "GENUINE skill gaps (no supporting evidence anywhere in "
                f"your profile -- these are not tailoring failures): "
                f"{', '.join(genuine_gaps)}."
            )
        if surfaceable_remaining:
            parts.append(
                "Surfaceable but still insufficient after retailoring: "
                f"{', '.join(surfaceable_remaining)}."
            )
        super().__init__(" ".join(parts))


def extract_jd_keywords(jd_text: str) -> list[MissingKeyword]:
    """Every curated-taxonomy skill the job description mentions.

    Returned hard-first (the ranking used everywhere downstream). Only
    taxonomy skills are *scored*; other JD phrasing surfaces via
    :func:`unrecognized_jd_terms` for a human eye, never the score.
    """
    found = [
        MissingKeyword(keyword=skill, kind="hard")
        for skill in sorted(HARD_SKILLS)
        if _occurrences(skill, jd_text) > 0
    ] + [
        MissingKeyword(keyword=skill, kind="soft")
        for skill in sorted(SOFT_SKILLS)
        if _occurrences(skill, jd_text) > 0
    ]
    return found


def unrecognized_jd_terms(jd_text: str, limit: int = 15) -> list[str]:
    """Capitalized/technical JD terms outside the taxonomy -- advisory only."""
    candidates: list[str] = []
    seen: set[str] = set()
    known = {_normalize(skill) for skill in HARD_SKILLS | SOFT_SKILLS}
    for token in re.findall(r"\b[A-Z][A-Za-z0-9.+#-]{2,}\b", jd_text):
        normalized = _normalize(token)
        if normalized in known or normalized in _STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(token)
    return candidates[:limit]


def score_resume(
    rendered_text: str,
    content: TailoredContent,
    profile: MasterProfile,
    *,
    opportunity_title: str,
    jd_text: str,
    threshold: float,
) -> AtsScoreReport:
    """The deterministic layer's whole judgment, as one pure function.

    ``rendered_text`` must be the exact string the human previews (the
    "one text, one truth" identity the pipeline proves by test) --
    keyword occurrences are counted against it. ``content``/``profile``
    supply section attribution (contextual vs skills-list-only) and
    completeness facts the plain-text preview doesn't carry (contact,
    education).
    """
    required = extract_jd_keywords(jd_text)
    contextual_text = " ".join(
        [content.summary]
        + [h for entry in content.work for h in entry.highlights]
        + [h for entry in content.projects for h in entry.highlights]
    )
    skills_text = " ".join(content.skills)

    matched: list[KeywordMatch] = []
    missing: list[MissingKeyword] = []
    stuffing_flags: list[str] = []
    earned = 0.0
    possible = 0.0
    for keyword in required:
        possible += keyword.weight
        occurrences = _occurrences(keyword.keyword, rendered_text)
        if occurrences == 0:
            missing.append(keyword)
            continue
        contextual = _occurrences(keyword.keyword, contextual_text) > 0
        in_skills = _occurrences(keyword.keyword, skills_text) > 0
        credit = 1.0 if contextual else (SKILLS_ONLY_CREDIT if in_skills else 1.0)
        if occurrences > STUFFING_OCCURRENCE_CAP:
            stuffing_flags.append(
                f"{keyword.keyword!r} appears {occurrences}x (cap "
                f"{STUFFING_OCCURRENCE_CAP}) -- repetition beyond the cap "
                f"earns nothing and reads as stuffing"
            )
        if not contextual and in_skills:
            stuffing_flags.append(
                f"{keyword.keyword!r} appears only in the skills list with "
                f"no supporting context in any summary/highlight"
            )
        earned += keyword.weight * credit
        matched.append(
            KeywordMatch(
                keyword=keyword.keyword,
                kind=keyword.kind,
                occurrences=occurrences,
                contextual=contextual,
                credit=credit,
            )
        )
    coverage = 100.0 if possible == 0 else (earned / possible) * 100.0

    title_tokens = [
        token
        for token in _normalize(opportunity_title).split()
        if token not in _STOPWORDS
    ]
    recent_position = content.work[0].position if content.work else ""
    alignment_text = _normalize(f"{content.summary} {recent_position}")
    aligned = sum(1 for token in title_tokens if token in alignment_text.split())
    title_alignment = (
        100.0 if not title_tokens else (aligned / len(title_tokens)) * 100.0
    )

    section_checks = [
        bool(profile.basics.name and profile.basics.email),  # contact
        bool(content.summary.strip()),  # summary
        bool(content.work),  # work (dates guaranteed by resolve_work_dates)
        bool(profile.education),  # education (profile fact, ADR-0033)
        bool(content.skills),  # skills
    ]
    section_completeness = (sum(section_checks) / len(section_checks)) * 100.0

    format_hard_failures: list[str] = []
    if not rendered_text.strip():
        format_hard_failures.append(
            "rendered text is empty -- nothing a parser could read"
        )
    format_safety = 0.0 if format_hard_failures else 100.0

    missing.sort(key=lambda keyword: (-keyword.weight, keyword.keyword))
    total = (
        _COVERAGE_WEIGHT * coverage
        + _TITLE_WEIGHT * title_alignment
        + _SECTIONS_WEIGHT * section_completeness
        + _FORMAT_WEIGHT * format_safety
    )
    return AtsScoreReport(
        total=total,
        threshold=threshold,
        keyword_coverage=coverage,
        title_alignment=title_alignment,
        section_completeness=section_completeness,
        format_safety=format_safety,
        matched=matched,
        missing_keywords=missing,
        stuffing_flags=stuffing_flags,
        format_hard_failures=format_hard_failures,
        unrecognized_jd_terms=unrecognized_jd_terms(jd_text),
    )


def verified_semantic_keywords(
    claims: list[SemanticKeywordClaim],
    missing_keywords: list[MissingKeyword],
    rendered_text: str,
) -> list[str]:
    """The A3 filter: only claims with a real, verbatim supporting phrase count.

    A claim survives only if (a) it targets a keyword actually in the
    missing list, and (b) its ``quoted_phrase`` exists as a literal
    (casefolded) substring of the resume text -- checked here,
    deterministically, never trusted from the model. Survivors are pruned
    from the retailor gap report (the concept is already present under
    other wording, so retailoring toward it would be noise); nothing about
    the gate decision changes (case A1).
    """
    missing_set = {keyword.keyword for keyword in missing_keywords}
    haystack = rendered_text.casefold()
    verified: list[str] = []
    for claim in claims:
        if claim.keyword not in missing_set:
            continue
        phrase = claim.quoted_phrase.strip().casefold()
        if phrase and phrase in haystack:
            verified.append(claim.keyword)
    return verified


def _profile_full_text(profile: MasterProfile) -> str:
    bits: list[str] = [profile.basics.summary or ""]
    for work in profile.work:
        bits.extend([work.name, work.position, *work.highlights])
    for skill in profile.skills:
        bits.extend([skill.name, *(skill.keywords)])
    for project in profile.projects:
        bits.extend([project.name, project.description or "", *project.highlights])
    for education in profile.education:
        bits.extend([education.institution, education.area or "",
                     education.study_type or ""])
    return " ".join(bits)


def classify_missing_keywords(
    missing_keywords: list[MissingKeyword],
    profile: MasterProfile,
) -> tuple[list[SurfaceableKeyword], list[str]]:
    """Split missing keywords into SURFACEABLE (profile-backed) vs GENUINE.

    SURFACEABLE: the keyword has real evidence somewhere in the full
    profile text -- the first tailoring pass simply didn't surface it
    (case B2); the returned evidence excerpt is the profile's own text.
    GENUINE: zero evidence anywhere in the profile (case B1) -- a skill
    gap, reported to the human, never to the drafter.
    """
    full_text = _profile_full_text(profile)
    surfaceable: list[SurfaceableKeyword] = []
    genuine: list[str] = []
    for keyword in missing_keywords:
        pattern = _keyword_pattern(keyword.keyword)
        match = pattern.search(_normalize(full_text))
        if match is None:
            genuine.append(keyword.keyword)
            continue
        surfaceable.append(
            SurfaceableKeyword(
                keyword=keyword.keyword,
                profile_evidence=_evidence_excerpt(keyword.keyword, profile),
            )
        )
    return surfaceable, genuine


def _evidence_excerpt(keyword: str, profile: MasterProfile) -> str:
    """The first profile string that actually mentions the keyword."""
    candidates: list[str] = [profile.basics.summary or ""]
    for work in profile.work:
        candidates.extend([f"{work.position} at {work.name}", *work.highlights])
    for skill in profile.skills:
        candidates.extend([skill.name, *skill.keywords])
    for project in profile.projects:
        candidates.extend(
            [project.name, project.description or "", *project.highlights]
        )
    for candidate in candidates:
        if candidate and _occurrences(keyword, candidate) > 0:
            return candidate
    return ""
