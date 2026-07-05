"""Phase 14 / ADR-0038: the deterministic Decide scorer."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.agents.planner.decide import (
    DecideFilters,
    DeterministicDecideScorer,
)
from career_agent.domain.models import Opportunity, Provenance
from tests.agents._profile_fixture import sample_master_profile

_NOW = datetime(2026, 7, 1, tzinfo=UTC)


def _opp(
    opportunity_id: str,
    *,
    description: str = "",
    source: str = "ats_api",
    company: str = "acme",
    location: str | None = None,
    remote: bool | None = None,
    posted_at: datetime | None = None,
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id=company,
        canonical_company=company,
        title="Engineer",
        source=source,
        source_url="https://example.invalid/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.invalid/api",
            extraction_confidence=1.0,
        ),
        ats_ref="n1",
        posted_at=posted_at,
        location=location,
        remote=remote,
        description_raw=description,
        discovered_at=_NOW,
    )


def _profile():
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    return profile


def test_profile_match_reuses_the_phase_10_taxonomy_machinery() -> None:
    """Python/Django/PostgreSQL/Docker are in the fixture profile;
    Kubernetes is not -- 4 of 5 required keywords covered = 80."""
    scorer = DeterministicDecideScorer()
    score = scorer.score(
        _opp("a", description="Python, Django, PostgreSQL, Docker, Kubernetes."),
        _profile(),
        now=_NOW,
    )
    assert score.profile_match == 80.0


def test_better_profile_match_outranks_at_equal_everything_else() -> None:
    scorer = DeterministicDecideScorer()
    strong = _opp("strong", description="Python, Django, PostgreSQL, Docker.")
    weak = _opp("weak", description="Kubernetes, Terraform, Rust.")
    included, excluded = scorer.rank([weak, strong], _profile(), now=_NOW)
    assert [opportunity.id for opportunity, _score in included] == ["strong", "weak"]
    assert excluded == []


def test_source_reliability_orders_authoritative_over_extracted() -> None:
    scorer = DeterministicDecideScorer()
    api = scorer.score(_opp("a", source="ats_api"), _profile(), now=_NOW)
    board = scorer.score(_opp("b", source="job_board"), _profile(), now=_NOW)
    hn = scorer.score(_opp("c", source="hn"), _profile(), now=_NOW)
    assert api.source_reliability > board.source_reliability > hn.source_reliability


def test_freshness_tiers_and_unknown_middle() -> None:
    scorer = DeterministicDecideScorer()
    fresh = scorer.score(
        _opp("a", posted_at=datetime(2026, 6, 29, tzinfo=UTC)), _profile(), now=_NOW
    )
    stale = scorer.score(
        _opp("b", posted_at=datetime(2026, 1, 1, tzinfo=UTC)), _profile(), now=_NOW
    )
    unknown = scorer.score(_opp("c", posted_at=None), _profile(), now=_NOW)
    assert fresh.freshness == 100.0
    assert stale.freshness == 30.0
    assert unknown.freshness == 50.0


def test_salary_transparency_is_a_bonus_never_a_parse() -> None:
    scorer = DeterministicDecideScorer()
    with_salary = scorer.score(
        _opp("a", description="Salary: competitive, range disclosed."),
        _profile(),
        now=_NOW,
    )
    without = scorer.score(_opp("b", description="Great team."), _profile(), now=_NOW)
    assert with_salary.salary_transparency == 100.0
    assert without.salary_transparency == 0.0


def test_blacklist_is_a_hard_exclude_with_a_named_reason_not_a_penalty() -> None:
    """The load-bearing filter guarantee: a blacklisted company is excluded
    outright -- even a perfect keyword match cannot outweigh it -- and the
    exclusion carries a named reason, never a silent drop."""
    scorer = DeterministicDecideScorer(
        DecideFilters(blacklist_companies=["Acme"])
    )
    perfect = _opp(
        "a", company="acme", description="Python, Django, PostgreSQL, Docker."
    )
    included, excluded = scorer.rank([perfect], _profile(), now=_NOW)
    assert included == []
    assert len(excluded) == 1
    assert "blacklisted" in excluded[0].exclude_reasons[0]


def test_remote_only_and_location_allowlist_hard_excludes() -> None:
    scorer = DeterministicDecideScorer(
        DecideFilters(remote_only=True, allowed_locations=["Bengaluru"])
    )
    onsite_elsewhere = _opp("a", location="London", remote=False)
    remote = _opp("b", location="Anywhere", remote=True)
    included, excluded = scorer.rank(
        [onsite_elsewhere, remote], _profile(), now=_NOW
    )
    assert [opportunity.id for opportunity, _score in included] == ["b"]
    assert len(excluded) == 1
    assert any("not in the allowed list" in r for r in excluded[0].exclude_reasons)
    assert any("remote-only" in r for r in excluded[0].exclude_reasons)


def test_ranking_is_deterministic_ties_broken_by_id() -> None:
    scorer = DeterministicDecideScorer()
    a, b = _opp("aaa"), _opp("bbb")
    first, _ = scorer.rank([b, a], _profile(), now=_NOW)
    second, _ = scorer.rank([a, b], _profile(), now=_NOW)
    assert [o.id for o, _s in first] == [o.id for o, _s in second] == ["aaa", "bbb"]
