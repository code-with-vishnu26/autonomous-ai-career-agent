"""ADR-0045: Pareto-dominance analysis over a generic objective-point set.

Property/metamorphic tests are the load-bearing ones here (permutation
invariance, monotonicity, dominance-set stability under an irrelevant
addition) -- a dominance algorithm that gets these wrong is wrong
regardless of how many example-based tests happen to pass.
"""

from __future__ import annotations

import itertools

from career_agent.domain.pareto import (
    DominanceExplanation,
    ObjectivePoint,
    ParetoFrontier,
    analyze_frontier,
    pareto_dominates,
    robustly_dominates,
)


def _point(id_: str, **objectives: float) -> ObjectivePoint:
    return ObjectivePoint(id=id_, objectives=objectives)


# --- pareto_dominates: the pairwise primitive ------------------------------


def test_strictly_better_on_every_objective_dominates() -> None:
    a = _point("a", x=80.0, y=90.0)
    b = _point("b", x=70.0, y=80.0)
    assert pareto_dominates(a, b)
    assert not pareto_dominates(b, a)


def test_equal_points_do_not_dominate_each_other() -> None:
    a = _point("a", x=50.0, y=50.0)
    b = _point("b", x=50.0, y=50.0)
    assert not pareto_dominates(a, b)
    assert not pareto_dominates(b, a)


def test_mixed_better_and_worse_is_not_dominance() -> None:
    a = _point("a", x=90.0, y=10.0)
    b = _point("b", x=10.0, y=90.0)
    assert not pareto_dominates(a, b)
    assert not pareto_dominates(b, a)


def test_no_shared_objectives_never_dominates() -> None:
    a = _point("a", x=100.0)
    b = _point("b", y=100.0)
    assert not pareto_dominates(a, b)
    assert not pareto_dominates(b, a)


def test_disjoint_objectives_are_ignored_not_invented() -> None:
    """A objective only one point carries is neither a win nor a loss --
    dominance is judged only on what both actually share."""
    a = _point("a", x=90.0, y=90.0, extra=1.0)
    b = _point("b", x=80.0, y=80.0)
    assert pareto_dominates(a, b)


# --- robustly_dominates: the confidence-interval refinement ----------------


def test_full_confidence_robust_dominance_matches_nominal() -> None:
    a = ObjectivePoint(id="a", objectives={"x": 90.0}, confidence=1.0)
    b = ObjectivePoint(id="b", objectives={"x": 80.0}, confidence=1.0)
    assert pareto_dominates(a, b)
    assert robustly_dominates(a, b)


def test_low_confidence_can_defeat_a_nominal_win() -> None:
    """A narrowly-better point with low confidence must not robustly
    dominate: its worst case may fall below the other's best case."""
    a = ObjectivePoint(id="a", objectives={"x": 55.0}, confidence=0.2)
    b = ObjectivePoint(id="b", objectives={"x": 50.0}, confidence=1.0)
    assert pareto_dominates(a, b)  # nominal: 55 > 50
    assert not robustly_dominates(a, b)  # a's wide low-confidence band overlaps


def test_robust_dominance_implies_nominal_dominance() -> None:
    """Robust dominance is strictly stronger: intervals only ever widen a
    point value, never narrow it, so a's worst case beating b's best case
    guarantees a's point value beats b's point value too."""
    cases = [
        (
            ObjectivePoint(id="a", objectives={"x": 95.0, "y": 90.0}, confidence=0.9),
            ObjectivePoint(id="b", objectives={"x": 40.0, "y": 30.0}, confidence=0.9),
        ),
        (
            ObjectivePoint(id="a", objectives={"x": 60.0}, confidence=1.0),
            ObjectivePoint(id="b", objectives={"x": 55.0}, confidence=1.0),
        ),
    ]
    for a, b in cases:
        if robustly_dominates(a, b):
            assert pareto_dominates(a, b)


# --- analyze_frontier: the whole-set analysis -------------------------------


def test_single_dominant_point_is_the_only_frontier_member() -> None:
    points = [
        _point("best", x=90.0, y=90.0),
        _point("mid", x=60.0, y=60.0),
        _point("worst", x=10.0, y=10.0),
    ]
    result = analyze_frontier(points)
    assert result.frontier_ids == ["best"]
    by_id = {e.id: e for e in result.explanations}
    assert by_id["mid"].dominated_by == ["best"]
    assert by_id["worst"].dominated_by == ["best", "mid"]
    assert by_id["best"].pareto_optimal is True


def test_mutually_non_dominated_points_are_all_on_the_frontier() -> None:
    """Classic Pareto tradeoff: neither point beats the other on every
    dimension, so both are frontier-optimal."""
    points = [
        _point("cheap_slow", cost=90.0, speed=10.0),
        _point("fast_expensive", cost=10.0, speed=90.0),
    ]
    result = analyze_frontier(points)
    assert set(result.frontier_ids) == {"cheap_slow", "fast_expensive"}


def test_adding_an_irrelevant_dominated_point_keeps_existing_frontier_members() -> None:
    """Metamorphic property (explicitly required, ADR-0045): a new point
    strictly dominated by an existing frontier member must not change
    who else is on the frontier."""
    base = [
        _point("a", x=90.0, y=10.0),
        _point("b", x=10.0, y=90.0),
    ]
    before = set(analyze_frontier(base).frontier_ids)

    irrelevant = _point("c", x=5.0, y=5.0)  # dominated by both a and b
    after = analyze_frontier([*base, irrelevant])
    assert before <= set(after.frontier_ids)
    assert "c" not in after.frontier_ids


def test_frontier_is_permutation_invariant() -> None:
    """Metamorphic property (explicitly required, ADR-0045): the frontier
    set must not depend on input order."""
    points = [
        _point("a", x=90.0, y=10.0),
        _point("b", x=10.0, y=90.0),
        _point("c", x=50.0, y=50.0),
        _point("d", x=5.0, y=5.0),
    ]
    frontiers = {
        tuple(sorted(analyze_frontier(list(perm)).frontier_ids))
        for perm in itertools.permutations(points)
    }
    assert len(frontiers) == 1  # every permutation produces the same set


def test_improving_a_maximize_objective_never_removes_frontier_membership() -> None:
    """Monotonicity (explicitly required, ADR-0045): improving one of a
    frontier member's own objectives, all else equal, must not push it off
    the frontier -- it can only ever help, never hurt, its own status."""
    base = [
        _point("a", x=90.0, y=10.0),
        _point("b", x=10.0, y=90.0),
        _point("c", x=50.0, y=50.0),
    ]
    result_before = analyze_frontier(base)
    was_optimal = "c" in result_before.frontier_ids

    improved = [
        _point("a", x=90.0, y=10.0),
        _point("b", x=10.0, y=90.0),
        _point("c", x=50.0, y=95.0),  # strictly improved
    ]
    result_after = analyze_frontier(improved)
    if was_optimal:
        assert "c" in result_after.frontier_ids
    # Either way, a strict improvement can only ever gain or hold frontier
    # membership -- never lose it while every other point is unchanged.
    assert was_optimal <= ("c" in result_after.frontier_ids)


def test_explanations_are_sorted_by_id_for_determinism() -> None:
    points = [_point("z", x=1.0), _point("a", x=2.0), _point("m", x=1.5)]
    result = analyze_frontier(points)
    assert [e.id for e in result.explanations] == ["a", "m", "z"]


def test_result_types_are_the_documented_public_types() -> None:
    result = analyze_frontier([_point("a", x=1.0)])
    assert isinstance(result, ParetoFrontier)
    assert isinstance(result.explanations[0], DominanceExplanation)
