"""Phase 21 (ADR-0047): decision-intelligence validation and benchmark tests.

Every case here is explicitly synthetic (hand-constructed or grid-
enumerated objective vectors) -- never a claim about real discovered
opportunities or real hiring outcomes. Findings are reported as exact
counts/proportions over a defined, deterministic benchmark set only.
"""

from __future__ import annotations

from research.decision_benchmarks import (
    OBJECTIVE_NAMES,
    dominated_fraction_in_top_k,
    exhaustive_dominance_vs_scalar_order_search,
    fragility_landscape,
    frontier_coverage_in_top_k,
    make_decision,
    scalar_rank_order,
    scalar_top1_is_dominated,
    scalar_total,
    top1_vs_runner_up_flips,
)


def _flat(**objectives: float) -> dict[str, float]:
    return dict.fromkeys(OBJECTIVE_NAMES, 0.0) | objectives


# ---------------------------------------------------------------------------
# RQ1/RQ2: the exhaustive counterexample search itself -- the single most
# important result this phase produces. This is the permanent regression:
# if a future change to Decide's weights or objective set ever breaks this
# invariant, this test (not just the research module) must fail.
# ---------------------------------------------------------------------------


def test_exhaustive_grid_finds_no_dominance_scalar_order_counterexample() -> None:
    """5^4 = 625 objective vectors, 625*625 = 390,625 ordered pairs checked
    exhaustively: whenever a dominates b, S(a) > S(b), with zero exceptions
    anywhere in the grid. This is a computed proof for this exact grid, not
    a general mathematical proof for all real numbers -- but combined with
    the algebraic argument in ADR-0047 (all four weights are strictly
    positive and the Pareto comparison uses exactly the same four
    objectives S sums over), it is the strongest evidence this project can
    produce without inventing data."""
    counterexamples = exhaustive_dominance_vs_scalar_order_search()
    assert counterexamples == []


def test_scalar_top1_is_never_dominated_hand_constructed() -> None:
    """A hand-constructed instance of the same invariant, independent of
    the grid search, using DeterministicDecideScorer-shaped values."""
    winner = make_decision(
        "winner",
        profile_match=90.0,
        source_reliability=90.0,
        freshness=90.0,
        salary_transparency=100.0,
    )
    tradeoff = make_decision(
        "tradeoff", profile_match=95.0, source_reliability=10.0,
        freshness=10.0, salary_transparency=0.0,
    )
    dominated = make_decision(
        "dominated", profile_match=50.0, source_reliability=50.0,
        freshness=50.0, salary_transparency=0.0,
    )
    decisions = [winner, tradeoff, dominated]
    assert scalar_rank_order(decisions)[0] == "winner"
    assert scalar_top1_is_dominated(decisions) is False


# ---------------------------------------------------------------------------
# RQ13: boundary/edge geometries named explicitly in the brief.
# ---------------------------------------------------------------------------


def test_equal_vectors_are_mutually_non_dominated_and_both_on_frontier() -> None:
    a = make_decision("a", **_flat(profile_match=50.0, source_reliability=50.0))
    b = make_decision("b", **_flat(profile_match=50.0, source_reliability=50.0))
    assert scalar_top1_is_dominated([a, b]) is False
    assert frontier_coverage_in_top_k([a, b], k=2) == 1.0


def test_all_mutually_non_dominating_tradeoffs_have_full_frontier_coverage() -> None:
    a = make_decision("a", **_flat(profile_match=100.0))
    b = make_decision("b", **_flat(source_reliability=100.0))
    c = make_decision("c", **_flat(freshness=100.0))
    decisions = [a, b, c]
    assert frontier_coverage_in_top_k(decisions, k=3) == 1.0
    assert dominated_fraction_in_top_k(decisions, k=3) == 0.0


def test_one_universal_dominator_dominates_every_zero_vector_peer() -> None:
    dominator = make_decision(
        "dominator", **_flat(profile_match=100.0, source_reliability=100.0,
                              freshness=100.0, salary_transparency=100.0)
    )
    peers = [
        make_decision(f"peer{i}", **_flat()) for i in range(5)
    ]
    decisions = [dominator, *peers]
    assert scalar_rank_order(decisions)[0] == "dominator"
    assert frontier_coverage_in_top_k(decisions, k=1) == 1.0
    assert dominated_fraction_in_top_k(decisions, k=6) == 5 / 6


def test_zero_valued_and_maximum_valued_objectives_do_not_crash() -> None:
    zero = make_decision("zero", **_flat())
    maxed = make_decision(
        "maxed", **_flat(profile_match=100.0, source_reliability=100.0,
                          freshness=100.0, salary_transparency=100.0)
    )
    assert scalar_total(_flat()) == 0.0
    assert scalar_total(
        _flat(profile_match=100.0, source_reliability=100.0,
              freshness=100.0, salary_transparency=100.0)
    ) == 100.0
    assert scalar_top1_is_dominated([zero, maxed]) is False


def test_frontier_coverage_handles_k_greater_than_candidate_count() -> None:
    a = make_decision("a", **_flat(profile_match=100.0))
    b = make_decision("b", **_flat(source_reliability=100.0))
    # k=50 requested over only 2 real candidates -- must not divide by 50.
    assert frontier_coverage_in_top_k([a, b], k=50) == 1.0
    assert dominated_fraction_in_top_k([a, b], k=50) == 0.0


def test_metrics_are_zero_not_an_error_on_empty_input() -> None:
    assert scalar_top1_is_dominated([]) is False
    assert frontier_coverage_in_top_k([], k=5) == 0.0
    assert dominated_fraction_in_top_k([], k=5) == 0.0


# ---------------------------------------------------------------------------
# RQ7: permutation invariance across the whole pipeline, not just
# analyze_frontier in isolation (already proven there, Phase 19) -- here,
# through scalar_rank_order and the disagreement metrics together.
# ---------------------------------------------------------------------------


def test_disagreement_metrics_are_permutation_invariant() -> None:
    import itertools

    a = make_decision("a", **_flat(profile_match=90.0, source_reliability=10.0))
    b = make_decision("b", **_flat(profile_match=10.0, source_reliability=90.0))
    c = make_decision("c", **_flat(profile_match=40.0, source_reliability=40.0))
    results = set()
    for perm in itertools.permutations([a, b, c]):
        decisions = list(perm)
        results.add(
            (
                tuple(scalar_rank_order(decisions)),
                scalar_top1_is_dominated(decisions),
                frontier_coverage_in_top_k(decisions, k=2),
                dominated_fraction_in_top_k(decisions, k=2),
            )
        )
    assert len(results) == 1  # every permutation of the same set agrees


# ---------------------------------------------------------------------------
# RQ4/RQ5: bounded, explicitly synthetic fragility landscape. Fixed,
# hand-authored triples -- no randomness, so no seed is needed; this is
# NOT a claim about real-world frequency, only about this specific,
# labeled synthetic set.
# ---------------------------------------------------------------------------


def test_fragility_landscape_reports_a_reachable_flip_for_a_close_pair() -> None:
    close_pair_case = (
        _flat(profile_match=70.0, source_reliability=40.0, freshness=60.0),
        _flat(profile_match=55.0, source_reliability=90.0, freshness=30.0,
              salary_transparency=100.0),
        _flat(profile_match=10.0, source_reliability=10.0, freshness=10.0),
    )
    observations = fragility_landscape([close_pair_case])
    assert len(observations) == 1
    observation = observations[0]
    assert observation.most_fragile_weight in {
        "profile_match", "source_reliability", "freshness", "salary_transparency",
    }


def test_fragility_landscape_reports_none_for_identical_top_two() -> None:
    """Zero margin, zero-effect weights on the tie -- no weight change can
    'flip' an already-exact tie into a different kind of tie."""
    tied_case = (
        _flat(profile_match=50.0, source_reliability=50.0),
        _flat(profile_match=50.0, source_reliability=50.0),
        _flat(profile_match=10.0),
    )
    observations = fragility_landscape([tied_case])
    assert observations[0].top_pair_flips  # 4 weights still evaluated
    for flip in observations[0].top_pair_flips:
        assert flip.current_margin == 0.0


# ---------------------------------------------------------------------------
# Stage 7: direct closed-form-vs-recomputation validation, one level above
# what tests/agents/test_sensitivity.py already proves (that suite proves
# correctness for one hand-built pair; this proves it holds for the
# specific #1-vs-#2 extraction path this project actually uses in cli.py).
# ---------------------------------------------------------------------------


def test_top1_vs_runner_up_breakeven_reconstructs_an_exact_tie() -> None:
    a = make_decision(
        "a", **_flat(profile_match=70.0, source_reliability=40.0, freshness=60.0)
    )
    b = make_decision(
        "b", **_flat(profile_match=55.0, source_reliability=90.0, freshness=30.0,
                      salary_transparency=100.0)
    )
    flips = top1_vs_runner_up_flips([a, b])
    reachable = [f for f in flips if f.breakeven_delta is not None]
    assert reachable  # this pair is deliberately constructed to be flippable
    for flip in reachable:
        from career_agent.agents.planner.sensitivity import _perturbed_total

        higher, lower = (a, b) if flip.higher_id == "a" else (b, a)
        new_higher = _perturbed_total(higher, flip.weight_name, flip.breakeven_delta)
        new_lower = _perturbed_total(lower, flip.weight_name, flip.breakeven_delta)
        assert abs(new_higher - new_lower) < 1e-9


def test_top1_vs_runner_up_flips_empty_for_fewer_than_two() -> None:
    assert top1_vs_runner_up_flips([]) == []
    assert top1_vs_runner_up_flips([make_decision("solo", **_flat())]) == []
