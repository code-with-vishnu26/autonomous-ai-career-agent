"""Phase 21 (ADR-0047): deterministic decision-intelligence validation.

This module answers the research questions Phase 21 was scoped to
investigate -- it does **not** implement a new ranking algorithm. Every
function here is a pure, deterministic analysis of Decide's *existing*
scalar scorer (ADR-0038) and ADR-0045's Pareto/sensitivity modules,
imported unmodified from production code, never reimplemented.

**Labeling discipline (rule 26, brief):** every benchmark case built here
is explicitly synthetic -- hand-constructed or grid-enumerated objective
vectors, never real discovered opportunities, never real historical
outcomes, never invented salary/probability data. Findings are reported as
counts/proportions over an explicitly-labeled synthetic benchmark set,
never generalized to "real jobs" or "real hiring outcomes."
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from career_agent.agents.planner.decide import (
    _FRESHNESS_WEIGHT,
    _PROFILE_MATCH_WEIGHT,
    _RELIABILITY_WEIGHT,
    _SALARY_BONUS_WEIGHT,
    DecisionScore,
)
from career_agent.agents.planner.sensitivity import RankFlipPoint, rank_flip_points
from career_agent.domain.pareto import ObjectivePoint, analyze_frontier

#: Decide's real, current weights, imported directly (never duplicated) so
#: every benchmark case is scored exactly the way production code scores
#: it, not an approximation of it.
WEIGHTS: dict[str, float] = {
    "profile_match": _PROFILE_MATCH_WEIGHT,
    "source_reliability": _RELIABILITY_WEIGHT,
    "freshness": _FRESHNESS_WEIGHT,
    "salary_transparency": _SALARY_BONUS_WEIGHT,
}
OBJECTIVE_NAMES: tuple[str, ...] = tuple(WEIGHTS)
#: Every current real Decide objective is bounded to this range (decide.py,
#: confirmed by direct code inspection, not assumed).
OBJECTIVE_BOUNDS = (0.0, 100.0)


def scalar_total(objectives: dict[str, float]) -> float:
    """``S(o) = sum_k w_k * x_k(o)`` -- Decide's exact scalar formula."""
    return sum(WEIGHTS[name] * value for name, value in objectives.items())


def make_decision(opportunity_id: str, **objectives: float) -> DecisionScore:
    """Build a real ``DecisionScore`` for a synthetic objective vector.

    Scored with Decide's real weights -- never a hand-picked ``total``.
    """
    return DecisionScore(
        opportunity_id=opportunity_id,
        total=scalar_total(objectives),
        excluded=False,
        **objectives,
    )


def objective_point(
    decision: DecisionScore, *, confidence: float = 1.0
) -> ObjectivePoint:
    """Adapt a ``DecisionScore`` into ``domain.pareto``'s generic input.

    The exact same adapter shape as ``cli.py``'s ``_objective_point``
    (ADR-0046), reimplemented here (not imported) only because ``cli.py``
    is a composition root this offline module should not depend on.
    """
    return ObjectivePoint(
        id=decision.opportunity_id,
        objectives={name: getattr(decision, name) for name in OBJECTIVE_NAMES},
        confidence=confidence,
    )


def dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    """Nominal Pareto dominance over two raw objective dicts.

    All 4 keys are assumed present in both -- the invariant search's own
    precondition.
    """
    at_least_one_better = False
    for name in OBJECTIVE_NAMES:
        if a[name] < b[name]:
            return False
        if a[name] > b[name]:
            at_least_one_better = True
    return at_least_one_better


# ---------------------------------------------------------------------------
# RQ1/RQ2: can the scalar winner be dominated, or a dominated candidate
# outrank a Pareto-optimal one? -- exhaustive finite-grid counterexample
# search, not a sample.
# ---------------------------------------------------------------------------

#: Grid arithmetic (shown, not hidden): |G|=5 values per objective, d=4
#: objectives -> |G|^d = 5^4 = 625 possible objective vectors. This search
#: checks every ORDERED PAIR of vectors for the dominance-vs-scalar-order
#: invariant: 625 * 625 = 390,625 pairs, each an O(d)=O(4) check --
#: exhaustive and exact, no sampling, no combinatorial explosion (this is
#: NOT n candidates ranked together; it is one universal pairwise check
#: over the full grid, independent of how many opportunities a real run
#: would ever rank at once).
_GRID_VALUES: tuple[float, ...] = (0.0, 25.0, 50.0, 75.0, 100.0)


@dataclass(frozen=True)
class DominanceOrderCounterexample:
    """A pair where ``a`` dominates ``b`` but ``S(a) <= S(b)``.

    If this dataclass is ever actually instantiated by the search below,
    the "dominance implies higher scalar score" invariant is false.
    """

    dominant: dict[str, float]
    dominated: dict[str, float]
    dominant_total: float
    dominated_total: float


def exhaustive_dominance_vs_scalar_order_search() -> list[DominanceOrderCounterexample]:
    """Exhaustive grid search for a dominance-vs-scalar-order counterexample.

    Tests: whenever ``a`` Pareto-dominates ``b`` on Decide's exact 4
    objectives, is ``S(a) > S(b)``? Returns an empty list if (and only if)
    no counterexample exists anywhere in the 390,625-pair grid -- an
    empirically-verified proof for this grid, not merely a hand-derived
    algebraic claim.
    """
    vectors = [
        dict(zip(OBJECTIVE_NAMES, combo, strict=True))
        for combo in itertools.product(_GRID_VALUES, repeat=len(OBJECTIVE_NAMES))
    ]
    totals = [scalar_total(vector) for vector in vectors]
    counterexamples: list[DominanceOrderCounterexample] = []
    for i, a in enumerate(vectors):
        for j, b in enumerate(vectors):
            if i == j:
                continue
            if dominates(a, b) and not (totals[i] > totals[j]):
                counterexamples.append(
                    DominanceOrderCounterexample(a, b, totals[i], totals[j])
                )
    return counterexamples


# ---------------------------------------------------------------------------
# RQ4/RQ5: top-1-vs-runner-up weight fragility across a bounded, explicitly
# synthetic set of ranked triples (not exhaustive -- state space for full
# n-candidate enumeration is unbounded in n; this samples ranked *sets*
# deterministically, fixed seed, clearly labeled as a bounded exploration,
# never presented as a real-world frequency).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FragilityObservation:
    """One ranked set's #1-vs-#2 sensitivity outcome."""

    decisions: tuple[DecisionScore, ...]
    top_pair_flips: tuple[RankFlipPoint, ...]
    most_fragile_weight: str | None  # None if no weight could reach a flip


def top1_vs_runner_up_flips(decisions: list[DecisionScore]) -> list[RankFlipPoint]:
    """The exact #1-vs-#2 flip points for one already-ranked set.

    Reuses ``rank_flip_points`` unmodified and filters to that one pair
    (the same technique ``cli.py``'s ``_sensitivity_summary`` uses,
    ADR-0046).
    """
    if len(decisions) < 2:
        return []
    ranked = sorted(decisions, key=lambda d: (-d.total, d.opportunity_id))
    return [
        flip
        for flip in rank_flip_points(ranked)
        if flip.higher_id == ranked[0].opportunity_id
        and flip.lower_id == ranked[1].opportunity_id
    ]


def fragility_landscape(
    triples: list[tuple[dict[str, float], dict[str, float], dict[str, float]]],
) -> list[FragilityObservation]:
    """Run top1_vs_runner_up_flips over a list of synthetic candidate sets.

    Records which weight (if any) has the smallest-magnitude reachable
    breakeven for each 3-candidate objective-vector triple.
    """
    observations: list[FragilityObservation] = []
    for index, (v1, v2, v3) in enumerate(triples):
        decisions = (
            make_decision(f"case{index}-a", **v1),
            make_decision(f"case{index}-b", **v2),
            make_decision(f"case{index}-c", **v3),
        )
        flips = tuple(top1_vs_runner_up_flips(list(decisions)))
        reachable = [f for f in flips if f.breakeven_delta is not None]
        most_fragile = (
            min(reachable, key=lambda f: abs(f.breakeven_delta)).weight_name  # type: ignore[arg-type]
            if reachable
            else None
        )
        observations.append(FragilityObservation(decisions, flips, most_fragile))
    return observations


# ---------------------------------------------------------------------------
# RQ7: permutation invariance of scalar rank, frontier membership, and
# dominance explanations (sensitivity's own permutation invariance is
# proven separately -- rank_flip_points's *input* must already be sorted,
# so "permutation" for sensitivity means re-deriving the same sort first).
# ---------------------------------------------------------------------------


def scalar_rank_order(decisions: list[DecisionScore]) -> list[str]:
    """Decide's exact tie-break rule: total descending, id ascending."""
    return [
        d.opportunity_id
        for d in sorted(decisions, key=lambda d: (-d.total, d.opportunity_id))
    ]


# ---------------------------------------------------------------------------
# Disagreement metrics (Stage 6) -- only the ones with a rigorous,
# non-invented definition. No arbitrary "stable/unstable" threshold is
# introduced (brief's explicit instruction): raw deltas are exposed, not
# categorized.
# ---------------------------------------------------------------------------


def scalar_top1_is_dominated(decisions: list[DecisionScore]) -> bool:
    """``D_top``: is the scalar #1 pick NOT on the Pareto frontier?"""
    if not decisions:
        return False
    ranked = sorted(decisions, key=lambda d: (-d.total, d.opportunity_id))
    points = [objective_point(d) for d in decisions]
    frontier = analyze_frontier(points)
    top_explanation = next(
        e for e in frontier.explanations if e.id == ranked[0].opportunity_id
    )
    return not top_explanation.pareto_optimal


def frontier_coverage_in_top_k(decisions: list[DecisionScore], k: int) -> float:
    """``C_k = |TopK ∩ Frontier| / min(k, |Frontier|)``.

    Denominator semantics (stated explicitly, per the brief's own
    requirement): normalizes by the *smaller* of ``k`` and the frontier's
    actual size, so a frontier smaller than ``k`` can still score 1.0 when
    every frontier member is inside the top-k -- this metric asks "did the
    top-k *capture* the frontier," not "does the frontier fill k slots."
    Returns ``0.0`` (not a division error) when the frontier is empty.
    """
    if k <= 0 or not decisions:
        return 0.0
    ranked = sorted(decisions, key=lambda d: (-d.total, d.opportunity_id))
    top_k_ids = {d.opportunity_id for d in ranked[:k]}
    points = [objective_point(d) for d in decisions]
    frontier_ids = set(analyze_frontier(points).frontier_ids)
    if not frontier_ids:
        return 0.0
    denominator = min(k, len(frontier_ids))
    return len(top_k_ids & frontier_ids) / denominator


def dominated_fraction_in_top_k(decisions: list[DecisionScore], k: int) -> float:
    """``Q_k = |{o in TopK : o is dominated}| / |TopK|``.

    ``k > n`` is handled explicitly: the denominator is the *actual*
    number of candidates considered (``min(k, n)``), never the requested
    ``k`` itself, so asking for top-20 of a 3-candidate set does not
    silently report a fraction over an imaginary 20 slots.
    """
    if not decisions:
        return 0.0
    ranked = sorted(decisions, key=lambda d: (-d.total, d.opportunity_id))
    top_k = ranked[: max(k, 0)]
    if not top_k:
        return 0.0
    points = [objective_point(d) for d in decisions]
    frontier = analyze_frontier(points)
    dominated_ids = {
        e.id for e in frontier.explanations if not e.pareto_optimal
    }
    top_k_ids = [d.opportunity_id for d in top_k]
    dominated_count = sum(1 for id_ in top_k_ids if id_ in dominated_ids)
    return dominated_count / len(top_k_ids)
