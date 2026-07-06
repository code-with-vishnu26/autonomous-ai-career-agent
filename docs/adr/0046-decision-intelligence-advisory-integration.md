# ADR-0046: Pareto/sensitivity analysis wired in as an advisory-only layer (Phase 20)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0045](0045-pareto-dominance-and-weight-sensitivity-analysis.md)
  (the analysis capability this ADR integrates -- built additive, deliberately
  not wired to anything), [ADR-0038](0038-decide-layer.md) (the scalar scorer
  this ADR keeps authoritative for ordering), [ADR-0012](0012-opportunity-provenance-and-confidence.md)
  (`Provenance.extraction_confidence`, the evidence-quality signal this ADR
  surfaces honestly, not as a calibrated probability)

## Context

ADR-0045 built `domain/pareto.py` and `agents/planner/sensitivity.py` but
deliberately left them unwired -- a decision explicitly deferred, not an
oversight. Phase 20's repository audit (before any code was written) found:

- `DeterministicDecideScorer.rank()` (ADR-0038) is the sole ranking
  mechanism; hard exclusions (`_exclude_reasons`) are computed first and
  returned separately, unmodified.
- Ranked results reach a user in exactly one place: `run_discover_command`'s
  existing print block (`cli.py`), gated behind the already-optional
  `discover --profile` flag. No test asserts its exact output format.
- `run_auto_command` consumes only `included[:top_n]` -- pure scalar-order
  slicing -- to decide which opportunities get tailored, gated, and
  recorded. This is the one place a behavior change would carry real
  consequences (LLM calls, ATS-gate runs, database writes, notifications).
- Neither `domain.pareto` nor `agents.planner.sensitivity` was imported
  anywhere outside their own tests.

Six integration options were evaluated (full table in the implementation
report); the deciding factor was that every option touching `auto`'s
selection logic either violates ADR-0038's "keep `DeterministicDecideScorer`
authoritative" or collapses two independently-meaningful signals (a scalar
preference and a dominance relationship) into one, which Phase 19's own
scope explicitly warned against conflating.

## Decision

**Pareto/sensitivity analysis is now wired in as a read-only, advisory
annotation on `discover`'s existing ranked-summary output only.** Nothing
about `auto`'s selection, `DeterministicDecideScorer.rank()`'s output, or
hard-exclusion semantics changes.

1. **Scalar ranking remains authoritative for ordering and for `auto`'s
   selection**, unconditionally. `rank()`'s signature, sort order, and
   exclusion list are untouched by this ADR -- verified by running
   `tests/agents/test_decide.py`'s full existing suite unchanged and green.
2. **Dominance analysis is computed over the full `included` set**, never
   a display-truncated slice -- a lower-ranked opportunity outside a
   printed top-10 can still be the one that dominates a displayed one, and
   this ADR requires that not be silently missed (`_dominance_annotations`,
   `cli.py`).
3. **Sensitivity output is bounded to the #1-vs-#2 pair only** -- the
   single most decision-relevant question ("how fragile is my top pick")
   -- reusing `rank_flip_points` unmodified and filtering its output to
   that one pair, never dumping every adjacent pair's four weights.
4. **The evidence-quality band is labeled as a heuristic, never a
   calibrated probability**, printed once per run only when at least one
   displayed opportunity's `extraction_confidence` is below 1.0 -- this
   project has no historical accuracy data to calibrate a real interval
   against (same bar ADR-0039 and ADR-0045 both already set).
5. **Decision intelligence can never override feasibility.** Both new
   annotations are computed only from `included` (already past the hard
   exclusion gate); `excluded`'s reasons are printed exactly as before,
   untouched.
6. **`auto`'s behavior is unaffected**, structurally, not just by absence
   of a failing test: `run_auto_command`'s own code never calls
   `_dominance_annotations`/`_sensitivity_summary` at all (verified by a
   `co_names`-level test, the same discipline ADR-0041 used to prove
   `auto` cannot submit).

## What this does not do

- No wiring into `auto`'s selection (`included[:top_n]`) -- Option C/D from
  the audit, both rejected: a hard Pareto filter would violate "never
  weaken hard exclusions to include a formerly-excluded item, nor exclude
  a formerly-included one via a new, undocumented mechanism," and folding
  Pareto rank into the scalar score would silently redefine `total`
  without an explicit, separately-justified weighting decision.
- No new objectives invented -- exactly Decide's existing four
  (`profile_match`, `source_reliability`, `freshness`,
  `salary_transparency`).
- No portfolio/budget selection, no Monte Carlo, no calibrated
  probabilities -- all remain out of scope per ADR-0045's own reasoning,
  unchanged.
- No new CLI flags, no new command -- the existing `discover --profile`
  opt-in gate is reused exactly as it already was.

## Consequences

- `cli.py` gains three small, pure, tested functions (`_objective_point`,
  `_dominance_annotations`, `_sensitivity_summary`) and a caveat constant --
  the only place `DecisionScore`'s fields and
  `Opportunity.provenance.extraction_confidence` are adapted into
  `domain.pareto.ObjectivePoint`, since neither `pareto.py` nor
  `sensitivity.py` should know about the other's caller.
- Zero risk to `auto`'s real selection/tailoring/submission chain --
  verified both by the existing test suite passing unchanged and by a new
  structural (`co_names`) test.
- Zero cost, zero network, zero new dependency.
- Phase 19's own audit gap (no explicit test for `confidence=0.0`, equal
  confidence, or monotonicity under improved evidence quality) is closed
  in this ADR's implementation, with all four new tests passing against
  the *unmodified* Phase 19 code -- confirming the original implementation
  was already correct, not merely under-tested.
