"""Closed-form weight-sensitivity analysis for Decide's linear scorer (ADR-0045).

Decide's ``total(o) = w . x(o)`` is a linear function of its four fixed
weights (``agents/planner/decide.py``'s ``_PROFILE_MATCH_WEIGHT`` etc.).
Linearity means the question "how much would one weight have to change
before two adjacently-ranked opportunities swap order" has an *exact*
closed-form answer -- no search, no Monte Carlo sampling needed, which is
why this project's own bounded first slice of the "robustness/sensitivity"
research question (ADR-0045) implements only this, not a full
weight-simplex exploration (deferred, named, in the ADR).

**One-at-a-time, simplex-preserving perturbation**, as specified: perturbing
one weight ``w_k`` by ``delta`` while proportionally rescaling the other
three so they still sum to ``1 - (w_k + delta)`` -- preserving the
"weights sum to 1" invariant Decide's own weights already satisfy, rather
than an unconstrained perturbation that would silently stop being a
weighted average at all.

This module is Decide-specific (imports its weight constants and
``DecisionScore`` directly) and therefore lives beside ``decide.py`` in
``agents/planner/``, not in ``domain/`` -- unlike ``domain/pareto.py``,
there is nothing generic here to decouple; the whole point is Decide's
own four named weights and their sum-to-one constraint.
"""

from __future__ import annotations

from pydantic import BaseModel

from career_agent.agents.planner.decide import (
    _FRESHNESS_WEIGHT,
    _PROFILE_MATCH_WEIGHT,
    _RELIABILITY_WEIGHT,
    _SALARY_BONUS_WEIGHT,
    DecisionScore,
)

#: Decide's own weights, named -- must stay in sync with decide.py's
#: constants (imported directly, not duplicated, so they cannot drift).
_WEIGHTS: dict[str, float] = {
    "profile_match": _PROFILE_MATCH_WEIGHT,
    "source_reliability": _RELIABILITY_WEIGHT,
    "freshness": _FRESHNESS_WEIGHT,
    "salary_transparency": _SALARY_BONUS_WEIGHT,
}


class RankFlipPoint(BaseModel):
    """The exact perturbation of one weight at which an adjacent pair flips.

    All other weights rescaled proportionally to keep the sum at 1.
    ``breakeven_delta`` is ``None`` when no flip is reachable by
    perturbing this weight alone within its valid range ``[-w_k, 1-w_k]``
    -- either the line relating the pair's score gap to this weight is
    perfectly flat (this weight has zero effect on their relative order,
    which happens exactly when the two opportunities' difference on this
    objective equals their current total score gap), or the flip point
    falls outside what a valid weight value (each weight must stay within
    ``[0, 1]``) can reach.
    """

    higher_id: str
    lower_id: str
    weight_name: str
    current_weight: float
    current_margin: float
    breakeven_delta: float | None


def _perturbed_total(decision: DecisionScore, weight_name: str, delta: float) -> float:
    """``total(decision)`` under ``weight_name`` perturbed by ``delta``.

    The remaining three weights are rescaled proportionally to preserve
    ``sum(weights) == 1``.
    """
    w_k = _WEIGHTS[weight_name]
    new_w_k = w_k + delta
    scale = (1.0 - new_w_k) / (1.0 - w_k) if w_k != 1.0 else 0.0
    total = new_w_k * getattr(decision, weight_name)
    for name, w_j in _WEIGHTS.items():
        if name == weight_name:
            continue
        total += w_j * scale * getattr(decision, name)
    return total


def _breakeven_delta(
    higher: DecisionScore, lower: DecisionScore, weight_name: str
) -> float | None:
    """Exact zero-crossing of ``total(higher) - total(lower)`` in ``delta``.

    Computed from two evaluations (the difference is linear in ``delta``
    -- proven by construction: :func:`_perturbed_total` is an affine
    function of ``delta`` for fixed ``decision``, so the difference of two
    such functions is too), clamped to the range that keeps the perturbed
    weight a valid probability (``[0, 1]``).
    """
    w_k = _WEIGHTS[weight_name]
    y0 = _perturbed_total(higher, weight_name, 0.0) - _perturbed_total(
        lower, weight_name, 0.0
    )
    probe_delta = (1.0 - w_k) / 2.0 or 0.5  # any nonzero, in-range probe point
    y1 = _perturbed_total(higher, weight_name, probe_delta) - _perturbed_total(
        lower, weight_name, probe_delta
    )
    slope = (y1 - y0) / probe_delta
    if slope == 0.0:
        return None  # this weight has zero effect on this pair's order
    delta_star = -y0 / slope
    valid_range = (-w_k, 1.0 - w_k)
    if not (valid_range[0] <= delta_star <= valid_range[1]):
        return None  # flip is only reachable at an invalid (out-of-[0,1]) weight
    return delta_star


def rank_flip_points(ranked: list[DecisionScore]) -> list[RankFlipPoint]:
    """The exact breakeven perturbation for each adjacent pair and weight.

    ``ranked`` must already be sorted, best first. Only adjacent pairs are
    analyzed: a non-adjacent pair's relative order is not what determines
    the ranked list's current top-k membership, and is already implied
    transitively by the chain of adjacent margins.
    """
    points: list[RankFlipPoint] = []
    for higher, lower in zip(ranked, ranked[1:], strict=False):
        margin = higher.total - lower.total
        for weight_name, w_k in _WEIGHTS.items():
            points.append(
                RankFlipPoint(
                    higher_id=higher.opportunity_id,
                    lower_id=lower.opportunity_id,
                    weight_name=weight_name,
                    current_weight=w_k,
                    current_margin=margin,
                    breakeven_delta=_breakeven_delta(higher, lower, weight_name),
                )
            )
    return points
