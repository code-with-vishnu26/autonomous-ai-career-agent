# ADR-0034: ATS score gate — deterministic hard gate, advisory semantic layer, fabrication-proof retailor loop

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0016](0016-truthfulness-gate-verification.md) (the
  truthfulness gate this gate is sequenced strictly after, and the
  `ClaimVerifier` cost-cascade exemption whose reasoning this ADR
  deliberately does *not* extend to the semantic layer),
  [ADR-0031](0031-question-answerer.md) (the reviewer-drafted-matrix
  discipline and the structural channel-restriction pattern reused here),
  [ADR-0025](0025-resume-renderer.md) (the rendered text this gate scores),
  [ADR-0022](0022-resume-generator.md) (the drafter the retailor loop
  re-invokes, unchanged in its own guarantees)

## Context

Phase 10 of the standing master brief: an ATS-style score gate between the
truthfulness gate and render/confirm, with an auto-retailor loop. This is
the second-most safety-critical gate in the system after the truthfulness
gate itself, because it is the one place "raise the score" and "fabricate
to raise the score" sit dangerously close together. The adversarial test
matrix (14 cases, A1–D3) was drafted by the reviewer, not the implementer
— the same discipline as ADR-0016 and ADR-0031 — with four cases flagged
load-bearing: A1, B1, B3, C1.

## Decision

### Deterministic extraction over spaCy's statistical model (pre-brief finding 1)

The deterministic layer's keyword extraction is **curated-taxonomy
matching** (`domain/skills_taxonomy.py`, hard skills 2x / soft 1x) with
pure-Python normalization (case, hyphen/space, trailing-s) — no model
files. The decisive reason is not this sandbox's blocked model download
(403, verified) but reproducibility: a gate whose extraction depends on a
downloaded model artifact is only deterministic *conditional on* that
artifact's version — the same resume against the same JD could silently
score differently on a different machine or a later install, for reasons
unrelated to either. D1/D2's exact boundary behavior demands: same input,
same code version, same output, forever, anywhere. JD terms outside the
taxonomy surface as `unrecognized_jd_terms` — reported for a human eye,
never scored; spaCy noun-chunks remain a named, off-by-default future
enhancement (revisit criterion), not the load-bearing path.

### The gate decision is the deterministic score alone, period (pre-brief finding 2)

The standing brief's "semantic layer can only raise a score, never lower"
is self-contradictory the moment a raise crosses the threshold; matrix
case A1 (later, stricter, reviewer-authored) governs: **nothing the LLM
semantic layer produces can reach the pass/fail decision.** Composite:
keyword coverage 45%, title alignment 15%, section completeness 20%,
format safety 20%; `passed` is a **computed property of
`AtsScoreReport` itself** — `total >= threshold and not
format_hard_failures` — so both the threshold comparison (D1/D2: 74.99
fails, 75.00 passes) and the A2 hard-format-failure override live in the
type's own derivation, not caller discipline. The threshold is
`Settings.ats_threshold` (default 75.0, the brief's `ats.threshold`
flattened per the existing Settings shape), read at evaluation time (D3).

The semantic layer (`SemanticKeywordMatcher` port; real
`AnthropicSemanticKeywordMatcher` in `llm/`) runs only after a
below-threshold result, and its sole effect is pruning false-missing
keywords from the retailor gap report — each pruning requiring a quoted
phrase verified **verbatim against the resume text by deterministic
substring check** (`verified_semantic_keywords`, case A3: plausibility
alone is not evidence; an unverifiable claim is dropped). It fails
open-to-empty (advisory: "the advisor said nothing" is safe — the
opposite of the truthfulness gate's fail-closed, and correctly so,
because this layer blocks nothing).

### The B1 channel restriction: GENUINE gaps are structurally unreachable by the drafter

Missing keywords are classified deterministically against the full profile
text: **SURFACEABLE** (real profile evidence exists — the first pass just
didn't surface it) vs **GENUINE** (zero evidence anywhere — a skill gap,
not a tailoring gap). The `AtsGapReport` injected into a retailor prompt
has **exactly one content field: `surfaceable`** — there is no field
through which a GENUINE gap can reach the component that writes prose,
the same absence-of-the-channel guarantee as `answer_eeoc_question`
taking no `MasterProfile` parameter (ADR-0031). "Auto-retailor" cannot
become "auto-fabricate" because the fabrication targets are structurally
withheld; the full truthfulness gate still re-verifies every retry
independently — defense-in-depth, not the only wall. GENUINE gaps are
reported to the *human* (on the refusal error, named plainly as "not
tailoring failures"), never to the drafter.

### The loop: gate-before-score at every retry, convergence detection, honest refusal

`ResumeTailoringPipeline` (opt-in via `ats_threshold`, same
composition-root pattern as `artifacts_dir`): tailor → truthfulness gate →
ATS score → below threshold → re-draft with the SURFACEABLE-only gap
report → **full truthfulness gate again, before any scoring** — a
truthfulness-rejected retry is *never ATS-scored at all*; it consumes the
retry and the loop continues (B3: a high ATS score cannot bypass the
truthfulness gate because the score for an unapproved draft never
exists). Max 2 retries. A retry whose content is identical to the
previous attempt stops the loop early with "no further truthful
improvement available" (B5) rather than burning the remaining retry on an
identical draft and reporting it as a real attempt. Exhaustion raises the
typed `AtsScoreBelowThresholdError` carrying the full score trajectory
(B4: e.g. "60.00 -> 69.00 -> 78.00"), the per-category breakdown, and the
GENUINE vs surfaceable-remaining split.

**One text, one truth:** exactly one `render_tailored_resume` call per
accepted draft; the literal same string object is what the scorer
receives and what lands on `TailoredResume.rendered_text` — proven by a
reviewer-required identity test (`is`, not `==`), not assumed from two
calls that happen to agree today.

### Anti-stuffing (C1/C2)

A keyword's coverage credit never scales with repetition; occurrences
beyond 3 add a stuffing flag and nothing else. A keyword matched *only*
in the skills list with zero contextual occurrence in the summary or any
highlight earns half credit and flags — a bare keyword dump is not the
same evidence as a keyword doing real work in a sentence, and stuffing
truthful keywords is still dishonest presentation.

### `SemanticKeywordMatcher` is NOT cost-cascade-exempt — the reasoning, recorded

`ClaimVerifier`'s permanent exemption (ADR-0016) exists to protect
*judgments that gate something*, where a cheaper model's false approval
is unrecoverable downstream. This port gates nothing: its every claim is
deterministically re-verified (verbatim-phrase check), and nothing it
produces can reach the pass/fail decision (A1) — a wrong answer costs at
most one wasted retailor suggestion. The exemption's purpose does not
apply, so the exemption is not granted. Recorded as reasoning, not just
decision, per explicit reviewer requirement — a future reader should
understand *why* two LLM ports adjacent to gates carry different
exemption status, not merely observe it.

### Retailor prompt injection

`ResumeGenerator.tailor`/`ContentDrafter.draft` gain optional keyword-only
`gap_report` (backward compatible; prompt version bumped to
`resume-draft-v2`). The gap section interpolates only
`AtsGapReport.surfaceable` — keyword plus the profile's own evidence text
— under an explicit "surface ONLY where genuinely supported — never
invent" instruction. Because the type cannot carry a GENUINE gap, this
instruction can never name a fabrication target.

## Load-bearing verification (all four flagged cases, by injection)

- **A1** — injected: verified semantic claims add +20/keyword to the
  gating total. Caught: `test_case_a1_...` failed (`DID NOT RAISE` — the
  60-scoring draft sailed past the 99 threshold). Reverted.
- **B1** — injected: `classify_missing_keywords` appends GENUINE keywords
  to the surfaceable list. Caught: the drafter's own recorded calls showed
  Kubernetes in the injected gap report. Reverted.
- **B3** — injected: retry scored before the truthfulness gate, early
  return on a passing score. Caught: the fabricated draft got scored (3
  scorer calls, not 2). Independently, `to_submittable` would also have
  raised on the unapproved verdict — ADR-0018's structural wall backing
  the ordering test. Reverted.
- **C1** — injected: coverage credit multiplied by occurrence count.
  Caught: stuffed coverage 140 vs natural 60. Reverted.
- Post-revert: both touched files `diff`-verified byte-identical to
  pre-injection copies; full suite/ruff/import-linter re-run clean.

## Alternatives considered

- **spaCy noun-chunk extraction as the scored layer** (the brief's
  wording). Rejected for the hard gate: model-artifact-dependent
  determinism is not determinism (above). Named enhancement, off by
  default.
- **Blending the semantic layer into the score with a cap.** Rejected:
  any blend re-opens the A1 hole; pruning the gap report gives the layer
  real, useful work with zero authority.
- **Retrying on a truthfulness-rejected retry with a *fresh* gap report.**
  Rejected: the gap report derives from the last *scored* report; a
  rejected draft produced no new honest information to re-derive from.
- **Recording an audited `Application` for an ATS refusal** (like the
  truthfulness-rejection path). Deferred, not rejected: the typed error
  carries the full trajectory today; persisting refusals belongs with
  Phase 13's storage work, named there.

## Trade-offs

- **(+)** The gate is reproducible everywhere, the semantic layer is
  powerless over it by construction, and the retailor loop's fabrication
  channel is structurally absent — all four properties injection-proven.
- **(+)** Refusals are explainable: trajectory, per-category breakdown,
  and an honest "these are skill gaps, not tailoring gaps" split.
- **(−)** Coverage is bounded by the curated taxonomy: a JD skill outside
  it is invisible to the score (visible in `unrecognized_jd_terms`).
  Extending the taxonomy is a reviewed code change by design.
- **(−)** Title alignment is token-overlap only; a semantically-equivalent
  title phrased differently under-scores. Accepted at 15% weight.
- **(−)** The semantic layer costs one Claude call per below-threshold
  attempt when configured; skipped entirely when no matcher is wired.

## Consequences

- `domain/skills_taxonomy.py`, `domain/ats_scoring.py` (new, pure):
  models (`AtsScoreReport`, `AtsGapReport`, `SemanticKeywordClaim`,
  `MissingKeyword`, `KeywordMatch`, `SurfaceableKeyword`), scoring,
  classification, verbatim verification, `AtsScoreBelowThresholdError`.
- `core/interfaces.py`: `SemanticKeywordMatcher` port; `gap_report` param
  on `ResumeGenerator.tailor`/`ContentDrafter.draft`.
- `agents/resume/pipeline.py`: the gate + retailor loop.
- `llm/semantic_matcher.py` (new), `llm/prompts.py`
  (`resume-draft-v2` + gap section + semantic prompt),
  `llm/content_drafter.py` (gap section interpolation).
- `core/config.py`: `Settings.ats_threshold = 75.0`.
- `cli.py`: wires threshold + semantic matcher; prints the refusal's gap
  report.
- `tests/domain/test_ats_scoring.py` + `tests/agents/test_ats_gate_loop.py`:
  the reviewer's 14 cases plus the identity test.

## Future revisit criteria

Revisit if:

- Real JDs routinely require skills outside the taxonomy — extend the
  curated list (ordinary reviewed change), or reopen heuristic/noun-chunk
  extraction as a *scored* layer with a recorded reproducibility answer.
- The user's real machine wants spaCy enrichment — it must be config-
  flagged and clearly marked as changing scores relative to the canonical
  deterministic layer.
- Phase 13 lands persistent storage — ATS refusals should then be
  recorded as audited attempts, not only raised.
- Phase 14 reuses the keyword machinery for opportunity ranking (the
  brief plans this) — reuse `extract_jd_keywords`/`classify_missing_
  keywords`, do not fork them.
- Real-world pass rates suggest 75 is mis-calibrated — change the config
  default, with data, not the mechanism.
