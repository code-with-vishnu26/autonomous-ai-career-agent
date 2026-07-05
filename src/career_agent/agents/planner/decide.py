"""The Decide step: deterministic opportunity ranking (Phase 14, ADR-0038).

ADR-0007 designed "Decide" as a swappable scoring step inside the Planner
boundary rather than a separate agent -- this is its first concrete
implementation. Deterministic, weighted, zero LLM calls (any escalation to
model judgment is its own future pre-brief, not assumed): the same
opportunity set against the same profile and filters ranks identically,
forever, at this code version -- the same reproducibility bar as the ATS
gate (ADR-0034).

**Profile match reuses Phase 10's keyword machinery** -- the standing
brief's explicit instruction ("no new algorithm"):
:func:`~career_agent.domain.ats_scoring.extract_jd_keywords` pulls the
posting's taxonomy skills and
:func:`~career_agent.domain.ats_scoring.classify_missing_keywords` decides
which of them the profile actually evidences. One extraction vocabulary
across Decide and the ATS gate means an opportunity ranked highly here is
one the gate downstream can actually pass -- two vocabularies would rank
jobs the gate then refuses.

**Config filters are hard excludes, not penalties**: a blacklisted
company, a non-allowed location, or a non-remote posting under
remote-only preference is *excluded with a named reason*, never merely
down-ranked -- a penalty can be outweighed by a great keyword match; an
exclude cannot. (Injection-verified: converting the blacklist to a soft
penalty is caught by the dedicated test.)

**Salary floor is deliberately absent** (named, not silently dropped):
``Opportunity`` has no structured salary field, and parsing salary floors
out of freeform description text is exactly the kind of
confident-guess-from-prose this project refuses everywhere else. A salary
*transparency bonus* (the posting visibly discusses pay at all) is honest
and cheap; a numeric floor filter becomes possible only if a structured
salary field is ever added -- an ADR-0038 revisit criterion.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from career_agent.domain.ats_scoring import (
    classify_missing_keywords,
    extract_jd_keywords,
)
from career_agent.domain.identity import normalize
from career_agent.domain.models import MasterProfile, Opportunity

_PROFILE_MATCH_WEIGHT = 0.50
_RELIABILITY_WEIGHT = 0.20
_FRESHNESS_WEIGHT = 0.20
_SALARY_BONUS_WEIGHT = 0.10

#: Source reliability: authoritative ATS/API data outranks aggregators,
#: which outrank freeform extraction (ADR-0012's confidence ordering,
#: applied to ranking).
_SOURCE_RELIABILITY: dict[str, float] = {
    "ats_api": 1.0,
    "yc": 0.9,
    "job_board": 0.7,
    "career_page": 0.7,
    "hn": 0.5,
    "web_search": 0.4,
}

_SALARY_PATTERN = re.compile(
    r"(\$|£|€|₹|\bUSD\b|\bEUR\b|\bGBP\b|\bINR\b|\bsalary\b|\bcompensation\b"
    r"|\bpay range\b)",
    re.IGNORECASE,
)


class DecideFilters(BaseModel):
    """Hard-exclude preferences (config-driven, ADR-0038).

    Empty collections mean "no restriction" -- absence of a preference is
    never treated as a preference.
    """

    blacklist_companies: list[str] = Field(default_factory=list)
    allowed_locations: list[str] = Field(default_factory=list)
    remote_only: bool = False


class DecisionScore(BaseModel):
    """One opportunity's deterministic rank score, fully explainable."""

    opportunity_id: str
    total: float
    profile_match: float  # 0-100
    source_reliability: float  # 0-100
    freshness: float  # 0-100
    salary_transparency: float  # 0 or 100
    excluded: bool
    exclude_reasons: list[str] = Field(default_factory=list)


class DeterministicDecideScorer:
    """ADR-0007's swappable Decide step, first concrete implementation."""

    def __init__(self, filters: DecideFilters | None = None) -> None:
        """Configure with hard-exclude filters (default: no restrictions)."""
        self._filters = filters or DecideFilters()

    def score(
        self,
        opportunity: Opportunity,
        profile: MasterProfile,
        *,
        now: datetime | None = None,
    ) -> DecisionScore:
        """Score one opportunity against the profile; hard excludes first."""
        exclude_reasons = self._exclude_reasons(opportunity)
        profile_match = _profile_match(opportunity, profile)
        reliability = _SOURCE_RELIABILITY.get(opportunity.source, 0.4) * 100.0
        freshness = _freshness(opportunity, now or datetime.now(UTC))
        salary = 100.0 if _SALARY_PATTERN.search(opportunity.description_raw) else 0.0
        total = (
            _PROFILE_MATCH_WEIGHT * profile_match
            + _RELIABILITY_WEIGHT * reliability
            + _FRESHNESS_WEIGHT * freshness
            + _SALARY_BONUS_WEIGHT * salary
        )
        return DecisionScore(
            opportunity_id=opportunity.id,
            total=total,
            profile_match=profile_match,
            source_reliability=reliability,
            freshness=freshness,
            salary_transparency=salary,
            excluded=bool(exclude_reasons),
            exclude_reasons=exclude_reasons,
        )

    def rank(
        self,
        opportunities: list[Opportunity],
        profile: MasterProfile,
        *,
        now: datetime | None = None,
    ) -> tuple[list[tuple[Opportunity, DecisionScore]], list[DecisionScore]]:
        """Rank includable opportunities; return excluded ones separately.

        Excluded opportunities are returned (with their named reasons),
        never silently dropped -- the visible-discard-pile discipline
        (ADR-0013) applied to ranking.
        """
        included: list[tuple[Opportunity, DecisionScore]] = []
        excluded: list[DecisionScore] = []
        for opportunity in opportunities:
            decision = self.score(opportunity, profile, now=now)
            if decision.excluded:
                excluded.append(decision)
            else:
                included.append((opportunity, decision))
        included.sort(key=lambda pair: (-pair[1].total, pair[0].id))
        return included, excluded

    def _exclude_reasons(self, opportunity: Opportunity) -> list[str]:
        reasons: list[str] = []
        company = normalize(opportunity.canonical_company)
        blacklist = {normalize(entry) for entry in self._filters.blacklist_companies}
        if company in blacklist:
            reasons.append(f"company {opportunity.canonical_company!r} is blacklisted")
        if self._filters.allowed_locations:
            location = normalize(opportunity.location or "")
            allowed = {
                normalize(entry) for entry in self._filters.allowed_locations
            }
            remote_ok = opportunity.remote is True
            if not remote_ok and not any(
                entry in location for entry in allowed if entry
            ):
                reasons.append(
                    f"location {opportunity.location!r} not in the allowed list"
                )
        if self._filters.remote_only and opportunity.remote is not True:
            reasons.append("remote-only preference and posting is not remote")
        return reasons


def _profile_match(opportunity: Opportunity, profile: MasterProfile) -> float:
    """Coverage of the posting's taxonomy skills by the profile's evidence.

    Phase 10's exact machinery, unforked: extract, then classify each
    required keyword as profile-evidenced (SURFACEABLE) or not (GENUINE).
    No required keywords at all scores a neutral 50 -- an unparseable or
    skill-free posting is neither a great nor a terrible match.
    """
    required = extract_jd_keywords(opportunity.description_raw)
    if not required:
        return 50.0
    surfaceable, genuine = classify_missing_keywords(required, profile)
    covered = len(surfaceable)
    return (covered / (covered + len(genuine))) * 100.0


def _freshness(opportunity: Opportunity, now: datetime) -> float:
    if opportunity.posted_at is None:
        return 50.0  # honest middle: unknown is not fresh and not stale
    age = now - opportunity.posted_at
    if age <= timedelta(days=7):
        return 100.0
    if age <= timedelta(days=30):
        return 60.0
    return 30.0
