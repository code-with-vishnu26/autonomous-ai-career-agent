# ADR-0016: Truthfulness gate verification — entailment, categories, and the
first probabilistic safety component

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0003](0003-truthfulness-gate.md) (the gate's original
  contract), [ADR-0006](0006-json-resume-master-profile.md) (the master
  profile as sole source of truth), [ADR-0011](0011-structured-tailored-content.md)
  (structured tailored content), [ADR-0012](0012-opportunity-provenance-and-confidence.md)
  / [ADR-0013](0013-held-candidate-mechanism.md) (the confidence-carrying
  pattern this ADR reuses a third time, not reinvents)

## Context

ADR-0003 (Phase 2) established the gate's contract but not its implementation:
`TruthfulnessGate.verify(draft, profile) -> TruthfulnessResult` has existed,
unimplemented, since Phase 2. This phase was deliberately brought forward ahead
of the JSON Resume master profile phase specifically because the gate is the
single most safety-critical piece of the system, and a tracked deliverable had
already been observed to survive multiple phases unnoticed once (the Phase 4
"Career Page Finder" gap) — the gate does not get that risk.

The reviewer-defined a 12-case adversarial fabrication matrix independently of
the implementer, the same governance already used for the HN held-candidate
matrix (ADR-0013) and the cross-source dedup branches (ADR-0014): the
implementation is built *against* the matrix, not the other way around.

## Problem

How does `verify()` decide whether every claim in a tailored resume is
traceable to the master profile — catching fabrication in all its forms
(absence, alteration, invented identity, composite stitching) while not
blocking honest rephrasing, generalization, or elaboration — and what harness
does the one genuinely probabilistic component in an otherwise structurally-
guaranteed architecture need?

## Decision

### Entailment over keyword matching

Every work/project highlight (`TailoredWorkEntry`/`TailoredProjectEntry`
highlights, one highlight = one atomic `Statement` per ADR-0011) is judged
*holistically* against the **union** of evidence reachable from its linked
profile entry — that entry's own highlights, plus the full skills list, plus
all projects — never checked field-by-field against isolated lookups. This is
what makes a composite fabrication (a real skill and a real achievement
stitched into an invented combined claim, case #10) fail because the added
detail is genuinely ungrounded, not because some unrelated fragment happens to
trip an unrelated rule. Skills-list membership is the one check kept
deterministic (normalized string presence in `profile.skills`) — no ambiguity
to adjudicate, no model call needed.

### Category rubric (extends ADR-0003's `RejectionReason.category`, values
already defined, meanings clarified and one value added)

| Category | Fires when the claim... |
|---|---|
| `skill_not_found` | names a skill/technology absent from `profile.skills` |
| `employer_mismatch` | misstates an employer's identity **or title**, or references a work entry not in the profile at all. **Explicitly extended to title, not just company identity** — a category whose real scope lives only in a chat transcript is exactly the kind of undocumented decision this project avoids. |
| `date_inconsistency` | states dates inconsistent with the linked entry — see the structural note below on why this rarely fires in practice |
| `metric_unsupported` | states a specific number (percentage, count, dollar amount, team size) not grounded in the profile, altered or invented |
| `evidence_missing` | any other unsupported detail (architecture, scope, technology) that isn't a metric, employer, date, or skill claim |
| `verification_failed` | **new.** Infrastructure failure (verifier timeout/error/malformed response) — not a content judgment, so kept as its own category rather than overloading a content category. "We couldn't check" is not the same claim as "we checked and it's unsupported." |

### Case #6 (extended dates) resolved structurally, not behaviorally — a
stronger guarantee than the matrix asked for

`TailoredWorkEntry` carries no date fields (unchanged from its Phase 2 shape:
`source_entry_id`, `position`, `highlights` only). A tailored entry therefore
**cannot independently assert dates** — they are always the linked profile
entry's own, by construction. Date fabrication in structured content is not
caught by the gate; it is impossible to construct in the first place. This is
tested as a model-shape assertion, not a gate-behavior test, and it is a
*stronger* guarantee than the matrix's originally-described behavioral check —
in keeping with this project's general preference for structural guarantees
over probabilistic ones wherever a structural one is available. (Not addressed
explicitly in the pre-brief that was approved; resolved here and flagged for
correction if a different answer — e.g. deliberately allowing dates in
`TailoredWorkEntry` for some future rendering reason — was intended.)

### Case #9 (skill listed, never demonstrated in a bullet) — resolved: approve

The master profile's skills list is first-class evidence in its own right —
ADR-0006 established it as the single source of truth for every applicant-
facing claim, and `SkillEntry` is a top-level section, not a derived index of
work-history bullets. Requiring a skill to *also* appear in a work bullet
before it can be used in generated content would over-restrict: a user who
correctly lists a skill (e.g. from a personal project not otherwise in their
work history) could never have it used, even though the profile itself vouches
for it. A highlight claiming skill usage is grounded if the skill is present in
`profile.skills` *and* nothing else in that highlight is unsupported — a
compound sentence mixing a grounded skill claim with an invented detail (a team
size, say) still fails as a whole, since each highlight is one atomic
`Statement` and there is no partial credit (fail-closed, per ADR-0003).

### `summary` (free text) — explicitly out of scope this phase, a tracked gap

Verifying arbitrary claims inside unstructured prose is a second extraction
problem (mirroring HN's text-extraction, not simple entailment against known
fields); building it now would blur this phase's actual deliverable. **Tracked,
not silently dropped — same discipline as Phase 4's Career Page Finder gap.**
**Coupling to Phase 8, recorded now so it cannot be independently reopened
unnoticed:** `ResumeGenerator` (Phase 8) must treat `summary` conservatively
(derived from `profile.basics` / an existing summary, not freely invented
prose) until this gap closes, or `summary` verification must land before Phase
8 ships. Whoever designs `ResumeGenerator` must read this note first.

### `ClaimVerifier` — the first safety component resting on model judgment, not
a structural guarantee

Every prior safety mechanism in this project (required `provenance`, the
AST-checked domain-purity test, the import-linter contracts proven to bite by
injecting a real violation, the required `canonical_company` field) is
*mechanically* enforced — the type system or a deterministic check makes the
wrong thing impossible to construct. An LLM-judged entailment check is
categorically different: it can be wrong, inconsistent between runs, or
degrade if the prompt drifts. This was evaluated against the alternative
(heuristic-only, as HN used) and rejected for this specific task: unlike HN
(where a false-hold is merely recoverable), a false-approve here is
catastrophic, and no heuristic can safely thread rephrase-vs-fabrication in
both directions at once — case #1 (approve) and case #10 (block) require
genuine semantic judgment, not pattern matching.

Given that, the harness around this one probabilistic component must match the
stakes. Five compensating controls, all required, none optional:

1. **`ClaimVerdict.confidence` is required, not optional.** Same pattern as
   `Provenance.extraction_confidence` and `HeldCandidate` — not invented a
   third way. `LLMTruthfulnessGate` treats sub-threshold confidence as
   unverified regardless of `verified`; a low-confidence "yes" is not trusted
   more than a "no" (default threshold `0.7`, tunable, documented as such).
2. **Any verifier failure is an explicit, tested block, never a silent pass.**
   `LLMTruthfulnessGate._check_claim` catches any exception from
   `verify_claim` and records a `verification_failed` rejection; the gate
   itself never crashes (a single failing statement does not abort
   verification of the rest of the draft) and never treats infrastructure
   failure as evidence of truthfulness.
3. **Permanently exempt from cost-cascade routing.** `AnthropicClaimVerifier`
   pins the most capable model tier as a module-level constant, with an
   explicit in-code comment warning against future cost-optimization routing
   it to a cheaper tier. This asymmetry (false-approve catastrophic,
   false-block merely inconvenient) is why this task never joins the
   Haiku→Sonnet→Opus cascade used elsewhere.
4. **Temperature 0, with divergence across time documented as expected.**
   Minimizes but does not eliminate run-to-run variance. Re-verifying the same
   claim against the same evidence may legitimately produce a different
   verdict across calls purely from model variance — an expected, disclosed
   limitation of resting correctness on model judgment, not a surprise to be
   discovered later.
5. **The promptfoo suite (`promptfoo/`) is the hard merge gate for the real
   implementation.** `FakeClaimVerifier`-backed pytest proves the
   *orchestration* is correct; it proves nothing about whether Claude actually
   judges these 12 cases correctly. `AnthropicClaimVerifier` must not be wired
   into the Phase 7 apply path until the promptfoo suite passes on live calls.
   Git-based prompt versioning starts on this prompt, now, not deferred
   further: `TRUTHFULNESS_GATE_PROMPT_VERSION` is a required field on every
   `TruthfulnessResult`, so a verdict is always reproducible against the exact
   prompt that produced it.

### `ClaimVerifier` is a narrow port, not the general cost-cascade client

Scoped to exactly this task (`verify_claim(statement_text, evidence) ->
ClaimVerdict`), not the general `llm/` Claude-cascade client the project stack
names. `AnthropicClaimVerifier`'s real implementation is free to eventually
delegate to that general client once it exists, without this phase needing to
build the whole cascade subsystem first — same YAGNI discipline as every prior
phase's scope boundary (4c-slice-3's ranking functions, not Planner wiring).

## Alternatives considered

- **Heuristic-only verifier** (no LLM). Rejected: cannot safely distinguish
  honest rephrasing from fabrication in both directions simultaneously; a
  false-approve is catastrophic in a way HN's false-holds were not.
- **`ClaimVerdict` without a confidence field.** Rejected: would make
  "verified" a bare, untrusted-worthy boolean from a probabilistic source —
  the opposite of the compensating-controls discipline this ADR requires.
- **Building the full `llm/` cost-cascade client before the gate.** Rejected
  as premature scope for this phase; the narrow port lets the gate ship
  without blocking on a larger subsystem.
- **Silently including `summary` verification in this phase's scope, or
  silently excluding it without a note.** Rejected either way: the first
  would have blurred this phase's actual deliverable with a second, harder
  extraction problem; the second would have repeated exactly the kind of
  silent scope drop this phase exists to prevent (Career Page Finder).

## Trade-offs

- **(+)** Composite fabrication is caught for the right reason (entailment
  against the evidence union), not by coincidence; date fabrication in
  structured content is structurally impossible, not merely caught; the
  gate's one probabilistic component has a harness proportionate to the
  stakes; a merge gate exists that separates "orchestration is correct" from
  "the model judges correctly."
- **(−)** `summary` remains an ungated door until a future phase closes it —
  mitigated by the explicit Phase 8 coupling recorded above, not eliminated.
  Model-judgment variance is a permanent, disclosed limitation, not a solved
  problem. The evidence-union approach means every highlight check sends more
  context to the model than a narrow field-by-field check would, at some
  latency/cost — accepted given the stakes.

## Consequences

- `interfaces.py`'s existing `TruthfulnessGate`/`ResumeGenerator`/
  `TailoredResumeDraft` types (Phase 2) are unchanged; this phase adds
  `ClaimVerdict` and `ClaimVerifier`, both additive.
- `TruthfulnessResult.prompt_version` is now a required field — touches every
  construction site (four pre-existing test call sites updated in this
  change), the same "required field forces universality visible in the diff"
  pattern as ADR-0012/0014.
- `RejectionReason.category` gains `verification_failed` — additive to the
  Literal, non-breaking.
- Phase 8's `ResumeGenerator` design is constrained by this ADR's `summary`
  coupling note before it starts.
- Phase 7's apply path may not wire in `AnthropicClaimVerifier` until the
  promptfoo suite passes on live calls (tracked separately from this ADR's
  merge).

## Future revisit criteria

Revisit if:

- `summary` verification is built, closing the named gap (and the Phase 8
  coupling constraint can then be relaxed).
- The general `llm/` cost-cascade client is built and `AnthropicClaimVerifier`
  is refactored to delegate to it.
- Confidence threshold or prompt text need tuning based on real promptfoo/
  production results — expected evolution, tracked via prompt version bumps.
- Model-judgment variance proves large enough in practice to need a
  multi-sample/voting mechanism rather than a single call per claim.
