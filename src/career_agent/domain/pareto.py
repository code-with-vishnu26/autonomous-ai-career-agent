"""Generic Pareto-dominance analysis over a set of scored candidates (ADR-0045).

This is a bounded first slice of the research track's **R4** item
(``ROADMAP.md``): Decide (Phase 14, ADR-0038) ranks opportunities with a
single weighted-sum scalar. That answers "which is better overall" but not
"is this opportunity beaten on *every* dimension by some other real
candidate" -- a structurally stronger, more defensible statement than a
scalar comparison, and the actual mathematical content of "multi-objective."

**Deliberately generic, not coupled to** Decide's own ``DecisionScore``
**or any other caller's scoring type.** This module lives in ``domain/``,
which the project's import-linter contract forbids from depending on
``agents``/``core``/``plugins``/anything else in the project -- so it
cannot import Decide's own score type without breaking that contract, and
should not want to anyway: a Pareto-dominance algorithm is a general tool,
not something that should know which specific scorer produced its input.
A caller adapts its own scored objects into :class:`ObjectivePoint`; this
module knows nothing about where the numbers came from.

**Scope, deliberately bounded (see ADR-0045 for the full audit):** this
implements Pareto dominance/frontier extraction and one confidence-derived
robustness refinement, both using only signals that already exist in this
project (Decide's four already-computed 0-100 "maximize" objectives, and
``Provenance.extraction_confidence`` -- ADR-0012 -- the one real,
populated-by-every-source evidence-quality signal). It does **not**
implement portfolio/budget selection (no budget signal exists yet in
``Settings`` -- R5's own unmet trigger), Monte Carlo/Bayesian uncertainty
(no historical accuracy data exists to calibrate against -- same bar as
ADR-0039's small-sample discipline), or bandits (explicitly deferred
elsewhere, unaffected by this work). All objectives here are assumed
"higher is better" -- a caller with a minimize-type objective must negate
it before constructing an :class:`ObjectivePoint`; this module does not
carry a min/max direction flag because every current real caller's
objectives are already oriented this way, and adding one now would be an
unused, untested abstraction (YAGNI).

Complexity: naive O(n^2 * d) pairwise dominance checks -- deliberately not
optimized. This project's own real operating scale is "tens of
applications, not thousands" per the Learn pillar's own docstring
(ADR-0039); n^2 at that scale is negligible, and optimizing it now would
be complexity added for appearance, not need.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: The interval each objective is assumed to range over, for confidence-
#: derived robustness bands. Every current real objective (Decide's four)
#: is 0-100; a future caller with a different native range would need its
#: own bounds, not assumed here.
_DEFAULT_BOUNDS = (0.0, 100.0)


class ObjectivePoint(BaseModel):
    """One candidate's position in objective space, for Pareto analysis.

    ``objectives`` maps a name to a value on a "higher is better" scale --
    every objective here is assumed already oriented that way (see module
    docstring). ``confidence`` (default ``1.0``, meaning "exact/fully
    trusted") is the one real evidence-quality signal this project has
    (``Provenance.extraction_confidence``); a caller with nothing
    comparable should simply omit it rather than invent a value.
    """

    id: str
    objectives: dict[str, float]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


def pareto_dominates(a: ObjectivePoint, b: ObjectivePoint) -> bool:
    """Nominal (point-value) Pareto dominance.

    ``a`` dominates ``b`` iff ``a`` is no worse than ``b`` on every
    objective both carry, and strictly better on at least one. Objectives
    present in only one of the two are ignored for that pair -- never
    invented, never treated as a tie or a loss.
    """
    shared = set(a.objectives) & set(b.objectives)
    if not shared:
        return False
    strictly_better_on_one = False
    for name in shared:
        a_val, b_val = a.objectives[name], b.objectives[name]
        if a_val < b_val:
            return False
        if a_val > b_val:
            strictly_better_on_one = True
    return strictly_better_on_one


def _confidence_interval(
    value: float, confidence: float, bounds: tuple[float, float]
) -> tuple[float, float]:
    """The confidence-derived band around ``value``.

    Linear shrinkage toward ``bounds`` proportional to ``(1 -
    confidence)`` -- an explicit, stated *assumption* (ADR-0045), not a
    calibrated statistical model: this project has no historical accuracy
    data yet to calibrate against. At ``confidence=1.0`` the interval
    collapses to the point value exactly; at ``confidence=0.0`` it widens
    to the full ``bounds`` range.
    """
    lo, hi = bounds
    slack = 1.0 - confidence
    lower = value - slack * (value - lo)
    upper = value + slack * (hi - value)
    return lower, upper


def robustly_dominates(
    a: ObjectivePoint,
    b: ObjectivePoint,
    *,
    bounds: tuple[float, float] = _DEFAULT_BOUNDS,
) -> bool:
    """Interval-robust Pareto dominance.

    ``a`` robustly dominates ``b`` only if ``a``'s *worst-case* (lower
    confidence-interval bound) is still at least ``b``'s *best-case*
    (upper bound) on every shared objective, and strictly greater on at
    least one -- i.e. ``a`` beats ``b`` even under the least favorable
    reading of ``a``'s data and the most favorable reading of ``b``'s.
    Strictly stronger than :func:`pareto_dominates` (every robust
    dominance is also a nominal one, never the reverse) since intervals
    only ever widen a point value, never narrow it.
    """
    shared = set(a.objectives) & set(b.objectives)
    if not shared:
        return False
    strictly_better_on_one = False
    for name in shared:
        a_lo, a_hi = _confidence_interval(a.objectives[name], a.confidence, bounds)
        b_lo, b_hi = _confidence_interval(b.objectives[name], b.confidence, bounds)
        if a_lo < b_hi:
            return False
        if a_lo > b_hi:
            strictly_better_on_one = True
    return strictly_better_on_one


class DominanceExplanation(BaseModel):
    """Why one candidate is or isn't on the Pareto frontier, by id only.

    Never a bare score -- every dominated candidate names exactly which
    other real candidates dominate it, nominally and (the stricter test)
    robustly, so a human can see the actual comparison, not just a verdict.
    """

    id: str
    pareto_optimal: bool
    dominated_by: list[str] = Field(default_factory=list)
    robustly_dominated_by: list[str] = Field(default_factory=list)


class ParetoFrontier(BaseModel):
    """The full dominance analysis over one candidate set."""

    frontier_ids: list[str]
    explanations: list[DominanceExplanation]


def analyze_frontier(
    points: list[ObjectivePoint], *, bounds: tuple[float, float] = _DEFAULT_BOUNDS
) -> ParetoFrontier:
    """Extract the Pareto frontier and a dominance explanation per candidate.

    Deterministic and permutation-invariant: the frontier set and every
    explanation depend only on the multiset of points, never on input
    order (verified by a dedicated test, not just asserted here).
    """
    explanations: list[DominanceExplanation] = []
    frontier_ids: list[str] = []
    for point in points:
        others = [p for p in points if p.id != point.id]
        dominated_by = sorted(
            p.id for p in others if pareto_dominates(p, point)
        )
        robustly_dominated_by = sorted(
            p.id for p in others if robustly_dominates(p, point, bounds=bounds)
        )
        is_optimal = not dominated_by
        explanations.append(
            DominanceExplanation(
                id=point.id,
                pareto_optimal=is_optimal,
                dominated_by=dominated_by,
                robustly_dominated_by=robustly_dominated_by,
            )
        )
        if is_optimal:
            frontier_ids.append(point.id)
    explanations.sort(key=lambda e: e.id)
    return ParetoFrontier(frontier_ids=sorted(frontier_ids), explanations=explanations)
