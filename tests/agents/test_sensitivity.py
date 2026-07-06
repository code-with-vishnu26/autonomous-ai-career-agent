"""ADR-0045: closed-form weight-sensitivity analysis for Decide's linear scorer.

The load-bearing property here is empirical, not just algebraic: for every
non-``None`` ``breakeven_delta`` this module computes, actually perturbing
that weight by that exact amount must flip (or exactly tie) the pair's
order -- proving the closed-form derivation is correct by reconstruction,
not merely trusting the algebra in the implementation.
"""

from __future__ import annotations

from career_agent.agents.planner.decide import DecisionScore
from career_agent.agents.planner.sensitivity import (
    _WEIGHTS,
    _perturbed_total,
    rank_flip_points,
)


def _score(
    opportunity_id: str,
    *,
    total: float,
    profile_match: float = 50.0,
    source_reliability: float = 50.0,
    freshness: float = 50.0,
    salary_transparency: float = 0.0,
) -> DecisionScore:
    return DecisionScore(
        opportunity_id=opportunity_id,
        total=total,
        profile_match=profile_match,
        source_reliability=source_reliability,
        freshness=freshness,
        salary_transparency=salary_transparency,
        excluded=False,
    )


def test_no_effect_weight_reports_none() -> None:
    """When two opportunities are identical on every objective, no weight
    perturbation can ever change their (zero) margin -- must report None,
    not a spurious breakeven."""
    higher = _score("a", total=50.0, profile_match=50.0, source_reliability=50.0)
    lower = _score("b", total=50.0, profile_match=50.0, source_reliability=50.0)
    points = rank_flip_points([higher, lower])
    assert all(p.breakeven_delta is None for p in points)
    assert all(p.current_margin == 0.0 for p in points)


def test_breakeven_delta_actually_flips_the_pairs_order() -> None:
    """The empirical proof: recompute both totals at (current_weight +
    breakeven_delta) and confirm the margin crosses zero (flips sign or
    ties), for every weight where a real breakeven was found."""
    higher = _score(
        "higher",
        total=0.5 * 70 + 0.2 * 40 + 0.2 * 60 + 0.1 * 0,
        profile_match=70.0,
        source_reliability=40.0,
        freshness=60.0,
        salary_transparency=0.0,
    )
    lower = _score(
        "lower",
        total=0.5 * 55 + 0.2 * 90 + 0.2 * 30 + 0.1 * 100,
        profile_match=55.0,
        source_reliability=90.0,
        freshness=30.0,
        salary_transparency=100.0,
    )
    points = rank_flip_points([higher, lower])
    assert len(points) == len(_WEIGHTS)

    found_a_real_flip = False
    for point in points:
        if point.breakeven_delta is None:
            continue
        found_a_real_flip = True
        new_total_higher = _perturbed_total(
            higher, point.weight_name, point.breakeven_delta
        )
        new_total_lower = _perturbed_total(
            lower, point.weight_name, point.breakeven_delta
        )
        # At the exact breakeven point the margin must be (numerically) zero.
        assert abs(new_total_higher - new_total_lower) < 1e-9

    assert found_a_real_flip  # this fixture is deliberately flippable


def test_breakeven_delta_is_none_when_outside_the_valid_weight_range() -> None:
    """A pair so far apart that no in-[0,1] weight value could ever flip
    their order via one weight alone must report None, not an
    out-of-range number presented as if it were reachable."""
    higher = _score(
        "higher",
        total=100.0,
        profile_match=100.0,
        source_reliability=100.0,
        freshness=100.0,
        salary_transparency=100.0,
    )
    lower = _score(
        "lower",
        total=0.0,
        profile_match=0.0,
        source_reliability=0.0,
        freshness=0.0,
        salary_transparency=0.0,
    )
    points = rank_flip_points([higher, lower])
    for point in points:
        if point.breakeven_delta is not None:
            assert -point.current_weight <= point.breakeven_delta <= (
                1.0 - point.current_weight
            )


def test_only_adjacent_pairs_are_analyzed() -> None:
    ranked = [
        _score("first", total=90.0),
        _score("second", total=60.0),
        _score("third", total=30.0),
    ]
    points = rank_flip_points(ranked)
    pairs = {(p.higher_id, p.lower_id) for p in points}
    assert pairs == {("first", "second"), ("second", "third")}


def test_current_margin_matches_the_scores_own_totals() -> None:
    higher = _score("a", total=80.0)
    lower = _score("b", total=55.0)
    points = rank_flip_points([higher, lower])
    assert all(p.current_margin == 25.0 for p in points)


def test_empty_and_singleton_rankings_produce_no_pairs() -> None:
    assert rank_flip_points([]) == []
    assert rank_flip_points([_score("only", total=50.0)]) == []
