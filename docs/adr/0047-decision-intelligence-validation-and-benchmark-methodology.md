# ADR-0047: Decision-intelligence validation methodology + a proven dominance/scalar-order invariant

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0045](0045-pareto-dominance-and-weight-sensitivity-analysis.md)
  (the Pareto/sensitivity modules validated here, unmodified),
  [ADR-0046](0046-decision-intelligence-advisory-integration.md) (the
  `discover`-output integration validated here, unmodified),
  [ADR-0038](0038-decide-layer.md) (the scalar scorer whose interaction
  with Pareto dominance this ADR formally proves)

## Context

Phase 21's purpose was not to add another algorithm, but to scientifically
validate ADR-0045/0046's decision-intelligence system: measure disagreement
between the scalar and Pareto lenses, search for counterexamples, audit
the sensitivity and robust-dominance implementations against direct
recomputation, and determine whether repository evidence justifies any
further algorithmic milestone. A repository audit (fresh reads, not
memory) confirmed `main` at `208973c` contains both Phase 19 (`7100fb6`)
and Phase 20 (`281ae73`) exactly as previously reported, with zero drift
since either merge.

## Decision: the central finding

**Under the current architecture, the scalar-ranking winner can never be
Pareto-dominated, and a Pareto-dominated candidate can never outrank its
dominator in scalar order.** This is a genuine mathematical property of
how ADR-0046 wired the two systems together, not an assumption:

**Proof sketch.** Decide's scalar score is `S(o) = Σ_k w_k · x_k(o)` over
exactly the same four objectives (`profile_match`, `source_reliability`,
`freshness`, `salary_transparency`) that `cli.py`'s `_objective_point`
adapter feeds into Pareto dominance — the same four keys, every time,
never a subset. If `a` Pareto-dominates `b` (`a_k ≥ b_k` for every `k`,
strictly for at least one), then since every weight `w_k` is strictly
positive (0.50, 0.20, 0.20, 0.10 — none zero, confirmed by direct
inspection of `decide.py`), `S(a) − S(b) = Σ_k w_k·(a_k − b_k) ≥ 0`, and
strictly positive at the one `k` where `a_k > b_k` and `w_k > 0` — so
`S(a) > S(b)` always. Since the scalar top-1 pick is (by definition) not
beaten in total by anything, and any dominator of it would beat it in
total by this proof, **the scalar top-1 is always Pareto-optimal.**

**This proof was verified two ways, not merely derived:**
1. Algebraically, above.
2. Computationally: `research/decision_benchmarks.py::exhaustive_dominance_vs_scalar_order_search`
   enumerates a `5^4 = 625`-vector grid (values `0, 25, 50, 75, 100` per
   objective) and checks all `625 × 625 = 390,625` ordered pairs for a
   counterexample. **Zero found**, in `~0.3s` — `tests/research/test_decision_benchmarks.py::test_exhaustive_grid_finds_no_dominance_scalar_order_counterexample`
   is the permanent regression for this.

**Caveat, stated precisely:** this proof covers *nominal* dominance
against the *scalar* order under the *current* weight/objective
correspondence. It says nothing about whether Decide's weights are the
*right* weights (a preference question, not a mathematical one), and
robust (confidence-interval) dominance is a *stricter* relation than
nominal (already proven in ADR-0045), so it inherits this same guarantee
automatically (proven dominance ⟹ nominal dominance ⟹ scalar order).

## What this answers from the research questions

- **RQ1/RQ2** (can the scalar winner be dominated; can a dominated
  candidate outrank a frontier one): **No**, provably, under the current
  architecture — not merely "not observed."
- **RQ3** (under what geometries does disagreement occur): only among
  **non-adjacent-to-#1** ranks — a rank-3 opportunity dominated by a
  rank-2 one is possible and expected (a genuine multi-objective
  tradeoff, not a bug), just never involving the #1 position itself.
- **RQ7** (permutation invariance): confirmed across the whole pipeline
  (scalar rank, frontier membership, and both new disagreement metrics
  together, not just `analyze_frontier` in isolation as Phase 19 already
  proved) — `test_disagreement_metrics_are_permutation_invariant`.
- **RQ8** (monotonic improvement never worsens Pareto/robust status):
  already proven for Pareto in Phase 19; this ADR's proof extends it to
  the scalar score too (monotonicity of `S` in each `x_k` is immediate
  from positive weights).
- **RQ9/RQ10** (evidence-quality monotonicity for robust dominance):
  re-confirmed with four new tests closing a real Phase 19 test-coverage
  gap (`confidence=0.0` both directions, equal confidence, monotonic
  improvement) — all passing against **unmodified** Phase 19 code.
- **RQ11** (hard exclusions invariant under advisory analysis): confirmed
  structurally — `_dominance_annotations`/`_sensitivity_summary` only ever
  receive `included`; a new test proves an excluded opportunity with a
  hypothetically dominating vector never appears anywhere in the ranked/
  advisory output, and a `co_names` test proves neither function is
  referenced by `confirm_submission`, `run_apply_command`, or
  `_apply_pipeline`.
- **RQ12** (explanation fidelity): re-confirmed — no unreachable
  sensitivity flip is ever presented as reachable (`_sensitivity_summary`
  only reports deltas from the `reachable`-filtered list, by construction).
- **RQ13** (edge geometries): equal vectors, universal dominator, all-
  mutually-non-dominating, zero/maximum-valued objectives, and duplicate
  objective vectors across distinct ids are all covered (the last one was
  a genuine Phase 19 test-coverage gap, now closed).
- **Stage 7 audit finding:** direct just-below/just-above-breakeven
  recomputation (a check Phase 19 didn't have) found the sign of the
  margin's slope in `delta` varies by weight and pair — an initial test
  draft that assumed a fixed slope direction failed against the real
  implementation and was corrected to a direction-agnostic check
  (`margin_below · margin_above < 0`). The implementation itself was
  never wrong; the first draft of this new test was, and was fixed before
  being trusted.

## Benchmark methodology (Stage 12 decision)

**Option B selected**: a pure-Python module (`research/decision_benchmarks.py`)
plus tests, not a new CLI command or report. Mirrors `promptfoo/`'s
existing precedent (a top-level directory adjacent to, not inside, the
installed `career_agent` package) rather than adding new production
surface for a validation-only concern. Every benchmark case is explicitly
synthetic; no real opportunity, outcome, or salary data is used or implied
anywhere in this module, and no statistical claim (p-value, confidence
interval, "significant," expected uplift) is made anywhere in its output —
only exact counts, proportions over the defined synthetic set, and exact
counterexamples (none found).

**This benchmark suite is now the required validation contract for any
future change to Decide's weights or objective set**: `test_exhaustive_grid_finds_no_dominance_scalar_order_counterexample`
must be re-run and must still pass (or the dominance/scalar-order
guarantee documented above must be explicitly revoked and re-documented)
before any such change ships.

## Future-algorithm evidence gate (Stage 14)

| Candidate | Repo signal supporting it | Missing prerequisite | Phase 21 finding that would justify it |
|---|---|---|---|
| Portfolio/knapsack optimization | None | No budget field in `Settings` | None found |
| Bayesian/conformal uncertainty | None | No historical accuracy data | None found |
| Monte Carlo / Sobol sensitivity | None | Closed-form already answers the one-at-a-time question exactly | None found — no case required simulation |
| Contextual bandits | None | N still "tens, not thousands" (ADR-0039) | None found |
| Learned ranking | None | No labeled outcome data | None found |
| Graph-based deduplication | None (unrelated to this phase) | No observed false-duplicate | Out of scope, unaffected |
| Hybrid retrieval | None (unrelated to this phase) | No observed missed-relevant-posting | Out of scope, unaffected |

**Conclusion: no additional algorithm is justified by this phase's
findings.** The one substantive result — the dominance/scalar-order
invariant — is a proof about the *existing* system's correctness, not a
gap calling for a new one.

## Consequences

- `research/decision_benchmarks.py` + `tests/research/test_decision_benchmarks.py`
  (new): the exhaustive counterexample search, disagreement metrics
  (`scalar_top1_is_dominated`, `frontier_coverage_in_top_k`,
  `dominated_fraction_in_top_k`, both with explicitly-stated denominator
  semantics), and a bounded, explicitly-synthetic sensitivity-fragility
  exploration.
- Four tests added to close a real Phase 19 audit gap
  (`tests/domain/test_pareto.py`), one to close a Phase 20 gap
  (`tests/test_cli_decision_intelligence.py`), two to strengthen Stage 7's
  direct-recomputation coverage (`tests/agents/test_sensitivity.py`).
- Zero change to `DeterministicDecideScorer`, hard exclusions, `auto`'s
  behavior, truthfulness semantics, or Promptfoo validation — this phase
  is pure validation and one new, tested, offline module.
- Zero cost, zero network, zero new dependency (`hypothesis` was
  considered and explicitly not added — not an existing dependency, and
  deterministic parameterization/exhaustive enumeration answered every
  question this phase needed without it).
