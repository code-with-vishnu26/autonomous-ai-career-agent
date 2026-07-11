# ADR-0068: Resume Variant Engine — deterministic cover letters + stored variants, built on the unmodified tailoring pipeline

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0023](0023-resume-tailoring-pipeline.md) (`ResumeTailoringPipeline`),
  [ADR-0025](0025-resume-renderer.md) (`render_tailored_resume`, the
  pure-rendering precedent this ADR mirrors), [ADR-0034](0034-ats-score-gate.md)
  (`ats_scoring`, `extract_jd_keywords` reused here unchanged),
  [ADR-0037](0037-persistence-discover-and-first-profile-writer.md) (`SqliteApplicationStore`, the
  storage-convention precedent), [ADR-0066](0066-website-adapter-framework.md)
  ("verified vs. stubbed" capability discipline)

## Context

Phase 50's goal: Job Found -> Extract Job Description -> Analyze Required
Skills -> Compare Against Master Profile -> Generate Tailored Resume ->
Generate Tailored Cover Letter -> Store Resume Variant -> Return Artifact to
Browser Layer. Nothing is submitted. "Extract job description," "analyze
required skills," and "compare against master profile" are already fully
built: `Opportunity.description_raw`, `ats_scoring.extract_jd_keywords`, and
`LLMResumeGenerator`/`TruthfulnessGate` respectively. "Generate tailored
resume" is `ResumeTailoringPipeline.run()`, unchanged since Phase 8b. What
this phase actually adds is the last three steps: a cover letter, a stored
variant, and a single call that returns both alongside the pipeline's
existing result.

## Decision

### The truthfulness gate is not extended to cover letters

`TruthfulnessGate`/`ClaimVerifier` and the deterministic Layer-1 precheck
(ADR-0044) are built and proven against one content shape:
`TailoredContent` — structured JSON-Resume-like fields where each highlight
is one atomic `Statement`. A cover letter is freeform paragraph prose.
Verifying it would mean either (a) atomizing arbitrary generated sentences
into checkable claims — an open, unsolved sub-problem, not a one-file
addition — or (b) gating the whole paragraph as one opaque unit, which
would catch a fabricated sentence only by rejecting sentences around it
too, a much weaker guarantee than the resume gate already provides.

**Decision: no new LLM call, no freeform generation, at all.** A cover
letter (`domain/cover_letter.py::assemble_cover_letter`) is assembled
**deterministically** from a `TailoredContent` that has *already* passed
the truthfulness gate — copying `content.summary` and up to three
`content.work[].highlights` verbatim into a templated letter shape. Every
sentence in the output already exists, word-for-word, in gate-approved
content. There is nothing new for a gate to verify, so none is added. Real
LLM-authored cover-letter prose — with its own atomization/verification
scheme — is explicit, named future work, not attempted here.

This is the same conservative move `AdapterCapabilities` made in Phase 48:
declare a narrower, honestly-scoped capability now (`assemble_cover_letter`,
a template) rather than guess at a wider one (`draft_cover_letter`, an LLM
call with no verification story).

### Company name: `opportunity.canonical_company`, no new `CompanyRepository`

`assemble_cover_letter` takes the full `Opportunity`, not a separate
`Company` lookup — `TieredApplicator.__init__`'s own docstring already
established "no separate `CompanyRepository` is introduced for this" when
it needed the same information; this reuses `canonical_company` (ADR-0014's
existing cross-source identity field) rather than reintroducing a lookup
this project deliberately never built.

### `select_closest_variant` is advisory only — it cannot touch the gate

`domain/resume_variants.py::select_closest_variant` ranks previously
*approved* `ResumeVariant`s by deterministic keyword overlap against the JD
(reusing `ats_scoring.extract_jd_keywords` unchanged — no new taxonomy, no
new matching algorithm). It is consulted once, purely for the
`closest_prior_variant` field on the result, so a caller/reviewer can see
"this is similar to a variant used before." **It is never fed back into
generation.** `ResumeVariantEngine.prepare` calls
`ResumeTailoringPipeline.run()` unconditionally, regardless of what (or
whether) a closest variant was found — reusing a close variant's content as
a generation shortcut is explicitly *not* built here. There is structurally
no path by which this ranking could influence what gets gated, matching
matrix-style reasoning the ATS gate already applies to its own semantic
layer (ADR-0034's "the LLM semantic layer never touches any number here").

### `ResumeVariantEngine` composes; it does not replace

`agents/resume/materials.py::ResumeVariantEngine.prepare()` wraps an
**injected, unmodified** `ResumeTailoringPipeline` — zero lines of
`pipeline.py`, `generator.py`, or `gate.py` changed. It runs the pipeline,
and only on approval: assembles a cover letter from the approved content,
and builds (but does not persist) a new `ResumeVariant`. This mirrors
`ResumeTailoringPipeline` itself, which composes `ResumeGenerator` +
`TruthfulnessGate` without either knowing the other exists.

### `SqliteResumeVariantStore` persists; `ResumeVariantEngine` never touches storage

Added directly into the existing `storage/sqlite.py` (the established
one-file convention for every SQLite store, `_connect` + a module-level
`_XXX_SCHEMA`), with `save`/`by_category`/`all_variants` — append-only,
`INSERT OR IGNORE` on `id`, the identical discipline
`SqliteApplicationStore.record` already applies.

`ResumeVariantEngine` deliberately has **no** dependency on this store, or
on `storage/` at all — an AST-based test (`test_materials_module_imports_no_storage`)
proves it. This mirrors an existing, unremarked fact about
`ResumeTailoringPipeline` itself: it never calls `application_store.record()`
either — `cli.py` does, at the composition root, after `pipeline.run()`
returns. `ResumeVariantEngine.prepare()` follows the identical shape:
it returns a built-but-unsaved `ResumeVariant` (Phase 50's "Store Resume
Variant" step's *data*); persisting it is the caller's job, the same as
every other store in this project. No new Protocol was introduced for this
either — `SqliteApplicationStore` itself is used concretely at the
composition root with no `ApplicationStore` Protocol in `core/interfaces.py`,
so a `ResumeVariantStore` Protocol would be inventing structure this
project's own established pattern does not use anywhere else.

## What this phase explicitly does not do

No CLI command wires any of this yet — same deliberate composition-root gap
Phase 48/49 both named and left open (wiring is its own decision, not free
to make inside an "engine" phase). No browser-layer artifact hand-off (`career_agent.integrations.browser`
is untouched). No reuse of a close variant's content as a generation
shortcut — `select_closest_variant`'s result is observational only. No
change to `ResumeTailoringPipeline`, `LLMResumeGenerator`,
`LLMTruthfulnessGate`, or any truthfulness-gate/ATS-gate code.

## Consequences

- Two new pure `domain/` modules (`cover_letter.py`, `resume_variants.py`),
  automatically covered by the existing AST-based domain-purity test suite
  (no test-file changes needed there).
- One new class in `storage/sqlite.py` (`SqliteResumeVariantStore`) plus its
  schema, following the file's existing convention exactly.
- One new orchestration module (`agents/resume/materials.py`,
  `ResumeVariantEngine`).
- 24 new tests: cover-letter assembly, closest-variant selection, the
  SQLite store's round-trip/append-only/reopen behavior, and the
  engine's composition (including a canary proving it imports no
  `storage` module).
- No new dependency, no version bump, no change to any existing file
  outside `storage/sqlite.py` (additive only).

## Future revisit criteria

Revisit cover-letter generation when a real content-verification scheme for
freeform prose is designed — the point at which real LLM-authored
cover-letter drafting (rather than deterministic reassembly) becomes safe
to build. Revisit `select_closest_variant`'s advisory-only boundary when/if
a future phase deliberately decides to use a close variant as a generation
shortcut — that is a new, separate safety decision (does reusing prior
content change what the truthfulness gate needs to check?), not a natural
extension of this one.
