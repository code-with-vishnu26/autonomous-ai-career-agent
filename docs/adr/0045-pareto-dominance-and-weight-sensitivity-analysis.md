# ADR-0045: Pareto-dominance frontier analysis + closed-form weight-sensitivity (Decide, bounded first slice of R4)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0038](0038-decide-layer.md) (the deterministic
  weighted-sum scorer this analysis is additive to, unmodified),
  [ADR-0012](0012-opportunity-provenance-and-confidence.md) (`Provenance.extraction_confidence`,
  the one real evidence-quality signal this ADR's uncertainty model uses),
  [ADR-0039](0039-learn-pillar.md) (the small-sample statistical-honesty
  discipline this ADR follows for its own uncertainty/sensitivity scope),
  `ROADMAP.md`'s Research track, item **R4** (the item this ADR is the
  first bounded slice of) and **R5**/**R6**/**R8** (the adjacent items this
  ADR explicitly does *not* implement, and why)

## Context

`ROADMAP.md`'s Research track already named this exact direction as
**R4 — Multi-objective decision engine**, with its own recorded trigger:
*"a Pareto/constrained-optimization model is real future work if soft-score
trading against hard constraints ever becomes an observed problem."* A
repository audit for this ADR found no such observed problem recorded
anywhere — no test, ADR, or commit documents a case where Decide's
weighted-sum ranking (`DeterministicDecideScorer`, ADR-0038) produced a
wrong answer a Pareto model would have corrected. **R5**'s own trigger
("no current daily/weekly application-budget constraint exists to
optimize against") is also unmet — `Settings` has no budget field, checked
directly. **R6**'s ("future work if/when N grows enough to matter") and
**R8**'s (bandits, "explicitly NOT started... no bandit routing until N is
sufficient") triggers are likewise unmet: the Learn pillar's own docstring
(ADR-0039) states this project's real operating scale as *"tens of
applications, not thousands."*

This means the full research-grade system originally proposed for this
milestone — portfolio/knapsack selection under a budget constraint, Monte
Carlo/Sobol sensitivity over the full weight simplex, Bayesian/conformal
uncertainty calibration, contextual bandits — is **not yet justified by
repository evidence**, and building it now would violate this project's
own repeatedly-enforced discipline (the same discipline that rejected
spaCy for artifact-non-determinism in ADR-0034, and rejects bandit routing
until N justifies it in ADR-0039).

What genuinely is real, already-computed, and already-tested: Decide
produces exactly four maximize-oriented, 0-100-bounded objectives per
opportunity (`profile_match`, `source_reliability`, `freshness`,
`salary_transparency` — `DecisionScore`), and every `Opportunity` carries a
real evidence-quality signal (`Provenance.extraction_confidence`,
ADR-0012) already populated by every discovery source, never invented for
this work. A genuinely mathematical, zero-invented-data, zero-cost
question can be asked of exactly this data today: **is a given opportunity
beaten on *every* dimension by some other real candidate** (a structurally
stronger, more defensible statement than "its scalar total is lower"), and
**how much would one Decide weight have to change before two adjacently-
ranked opportunities would swap order** (an exact, closed-form question,
since `total(o) = w . x(o)` is linear in the weights).

## Decision

Add two new, purely additive analysis modules. **Neither changes
`DeterministicDecideScorer`'s existing behavior, tested contract, or
output** — `rank()`'s signature, exclusion semantics, tie-breaking, and
every existing test in `tests/agents/test_decide.py` are untouched. Both
new modules are opt-in utilities a future caller may choose to run
*alongside* `rank()`'s existing output; **wiring them into `cli.py`'s
`discover`/`auto` output is explicitly deferred**, not part of this slice
— this ADR adds a new capability, not a new default behavior.

### 1. `domain/pareto.py` — generic Pareto-dominance analysis

Deliberately decoupled from `DecisionScore` (the import-linter contract
forbids `domain/` from depending on `agents/`, and a dominance algorithm
should not know which scorer produced its input regardless). Operates on
a generic `ObjectivePoint(id, objectives: dict[str, float], confidence:
float = 1.0)`.

**Nominal dominance:**

```
a ≻ b  iff  ∀ k ∈ shared(a,b): a_k ≥ b_k   and   ∃ k: a_k > b_k
```

Objectives present on only one side are ignored for that pair — never
treated as a win, a loss, or an invented tie.

**Confidence-derived interval (the uncertainty model, D):**

```
slack = 1 − confidence
lower(x, confidence) = x − slack · (x − lo)
upper(x, confidence) = x + slack · (hi − x)
```

with `[lo, hi] = [0, 100]` for every current real objective. This is an
**explicit, stated assumption**, not a calibrated statistical model — this
project has no historical accuracy data yet to calibrate a real interval
against (same evidentiary bar ADR-0039 sets for its own uncertainty
claims). At `confidence = 1.0` the interval collapses to the point value
exactly (a structured-API/feed opportunity, ADR-0012); at `confidence →
0.0` it widens toward the full `[0, 100]` range (an unreliable freeform
extraction).

**Robust dominance** (strictly stronger than nominal — proven, not just
asserted, by `test_robust_dominance_implies_nominal_dominance`):

```
a robustly≻ b  iff  ∀ k ∈ shared(a,b): lower(a_k) ≥ upper(b_k)   and   ∃ k: lower(a_k) > upper(b_k)
```

i.e. `a` beats `b` even under `a`'s least favorable reading and `b`'s most
favorable one.

`analyze_frontier(points) -> ParetoFrontier` returns the non-dominated set
plus, per point, a `DominanceExplanation` naming exactly which other real
candidates dominate it (nominally and robustly) — never a bare score.

**Complexity:** naive `O(n² · d)` pairwise comparison, deliberately not
optimized (no non-dominated-sorting-layer algorithm, no k-d tree pruning).
At this project's real scale — "tens of applications, not thousands"
(ADR-0039) — `n²` is negligible; optimizing it now would be complexity
added for appearance, not need, exactly what this ADR's own audit is
supposed to guard against.

### 2. `agents/planner/sensitivity.py` — closed-form weight-flip analysis

Decide-specific (imports `DecisionScore` and the four weight constants
directly), so it lives beside `decide.py`, not in `domain/`.

**One-at-a-time, simplex-preserving perturbation:** perturbing one weight
`w_k` by `δ` while rescaling the other three proportionally so the sum
stays 1:

```
w_k' = w_k + δ
w_j' = w_j · (1 − w_k − δ) / (1 − w_k)   for j ≠ k
```

Because `total(o)` under this perturbation is itself an affine function of
`δ` (verified two ways: algebraically, and empirically —
`test_breakeven_delta_actually_flips_the_pairs_order` recomputes both
totals at the derived breakeven point and asserts the margin is
numerically zero there), the breakeven `δ*` at which an adjacent pair's
margin crosses zero is solved **exactly from two evaluations of the
linear function**, not searched or simulated:

```
y(δ) = total'(higher, δ) − total'(lower, δ)      (affine in δ)
δ* = −y(0) / slope,   slope = (y(δ_probe) − y(0)) / δ_probe
```

`δ*` is reported as `None` (not a spurious number) when: the line is flat
(`slope == 0`, this weight has zero effect on this pair's order — happens
exactly when the two opportunities' difference on that one objective
equals their current total margin), or the flip point falls outside the
valid weight range `[-w_k, 1-w_k]` (no real, valid weight value could ever
reach it).

**Scope, deliberately bounded:** only adjacent pairs in the ranked list are
analyzed (a non-adjacent pair's order is already implied transitively by
the chain of adjacent margins, and is not what determines current top-k
membership); only one weight is perturbed at a time (a full joint-simplex
exploration — Monte Carlo or exhaustive grid sampling over `w ~
Distribution(simplex)`, estimating `P(rank(o_i) ≤ k)` — is real future
work, named here, not needed to answer today's one-at-a-time question, and
not justified by any observed need for it yet).

## What this explicitly does not do (named, not silently dropped)

- **No portfolio/budget selection** (R5): no budget signal exists in
  `Settings` yet. A knapsack/greedy/MMR-diversity selection step is future
  work if/when a real daily/weekly application-limit setting exists to
  optimize against.
- **No Monte Carlo/Bayesian/conformal uncertainty** (R6): this project has
  no historical accuracy data to calibrate a statistical model against.
  The confidence-interval model above is an explicit, stated assumption,
  not a fitted distribution — it must never be presented as calibrated
  statistical confidence.
- **No bandits** (R8): unaffected by this work; N still does not justify
  it, unchanged from ADR-0039's own reasoning.
- **No change to hard-exclude/feasibility logic**: `_exclude_reasons`
  (blacklist, location, remote-only) is Layer 0, untouched, and still the
  sole feasibility gate before any of this analysis ever runs.
- **No wiring into `cli.py`'s real `discover`/`auto` output.** Both new
  modules are tested, importable, and ready — exposing them in a real
  command's output is a separate, future, smaller decision (which format,
  which command, opt-in vs. default), deliberately not bundled into this
  ADR's scope.

## Consequences

- Two new, side-effect-free, dependency-minimal modules
  (`domain/pareto.py`: pydantic only; `agents/planner/sensitivity.py`:
  pydantic + `decide.py`'s own constants/type). Zero new external
  dependencies, zero network calls, zero cost.
- Zero risk to `DeterministicDecideScorer`'s existing, tested behavior —
  verified by running its full existing test suite unchanged and green.
- `ROADMAP.md`'s R4 entry is updated to record this as R4's first slice
  (the same convention R1 already uses), with the remaining, larger scope
  (portfolio selection, full-simplex sensitivity, calibrated uncertainty)
  named as still-proposed, still evidence-gated future work.
