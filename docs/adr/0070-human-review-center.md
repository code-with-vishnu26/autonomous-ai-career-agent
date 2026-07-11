# ADR-0070: Human Review Center — the sole READY_FOR_REVIEW → APPROVED boundary

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0018](0018-submission-safety.md) (`HumanConfirmation`'s
  named-token, no-default-to-yes discipline, reused here), [ADR-0026](0026-real-apply-command-and-promptfoo-enforcement.md)
  (`discover`'s opportunity-file handoff convention, extended here to
  `prepare` → `review`), [ADR-0037](0037-persistence-discover-and-first-profile-writer.md)
  (`SqliteApplicationStore`'s denormalized-display-fields precedent),
  [ADR-0068](0068-resume-variant-engine.md) (pure results living in
  `domain/`, "engine returns data, caller persists"), [ADR-0069](0069-application-preparation-engine.md)
  (`ApplicationSession`, the input this phase reviews; the AST-based
  no-click/no-browser-import structural-guarantee pattern reused here)

## Context

Phase 51 left `ApplicationSession` at `READY_FOR_REVIEW`/`BLOCKED`/
`LOGIN_REQUIRED_TIMEOUT`/`UNSUPPORTED_PROVIDER` — fully prepared, never
submitted, but with **no approval workflow**: nothing in the codebase
could act on a `READY_FOR_REVIEW` session at all. Phase 52 builds that one
missing transition: `READY_FOR_REVIEW` → `APPROVED`, and only ever by an
explicit human decision.

## Decision

### `ReviewSession` references, it does not duplicate

`ApplicationSession` already carries the résumé variant id, cover-letter
body, every filled/missing field, every uploaded file, and every warning
(Phase 51). A `ReviewSession` that copied all of that would create two
places the same content could drift apart. **Decision:** `domain/
review.py::ReviewSession` stores only `application_session_id` (the link)
plus a handful of cheap, denormalized display fields
(`company`/`job_title`/`provider`) — the identical precedent
`SqliteApplicationStore`'s own `company`/`title` columns already
established (denormalize identity fields for cheap queries, never full
content). The reviewed detail is always re-derived from the referenced
`ApplicationSession`, proven structurally: a test asserts `ReviewSession`
has no field named `warnings`/`missing_fields`/`filled_fields`/
`uploaded_files`/`resume_variant`/`cover_letter` at all.

### `format_review_summary`: pure, deterministic, hides nothing

`domain/review.py::format_review_summary` is a pure text-formatting
function over `ApplicationSession` — no LLM call, no filtering, no
prioritization. Every warning and every missing field is always printed;
there is no code path that could omit one. Lives in `domain/` (not
`agents/review/review_summary.py` as the brief's file list suggested),
matching the exact precedent `render_tailored_resume`/`assemble_cover_letter`
already set: pure formatting belongs in `domain/`, automatically covered
by the existing AST-based domain-purity test suite.

### `ReviewEngine`: no browser dependency, at all, structurally

**The single most safety-critical property of this phase.** `agents/
review/review_engine.py::ReviewEngine` never imports anything from
`career_agent.integrations.browser`, never sees a live Playwright `Page`,
and never calls a click method — proven by two source-scan tests
(`test_review_engine_imports_no_browser_module`,
`test_review_engine_never_calls_click`), the identical AST-based
structural-guarantee discipline `ApplicationPreparationEngine`'s own
no-click test already established (Phase 51). This is possible because
`ApplicationSession` is *already* fully serialized, browser-free data by
the time it reaches here — the review engine genuinely needs no browser
access to do its job, so none is given to it, not merely withheld by
convention.

Only an explicit "y"/"yes" (case-insensitive) answer produces `APPROVED`
— reusing `cli.py::confirm_submission`'s exact no-default-to-yes
discipline (ADR-0018): empty input, garbage input, and any other answer
all resolve to `REJECTED`, never a default "proceed." `CANCELLED`
(`KeyboardInterrupt`) and `TIMEOUT` (`TimeoutError`) are both reachable by
having `input_fn` raise — the engine has no timer of its own. A portable,
cross-platform bounded wait on interactive stdin is a real, separate
problem (`SIGALRM` is POSIX-only); rather than build something fragile,
`TIMEOUT` is proven reachable and handled correctly via an
injectable-exception seam, and the default `career-agent review` CLI
command waits indefinitely (identical to `confirm_submission`'s own
default behavior) — an honest, named scope boundary, not a silently
unimplemented state.

### No new `field_detector`/`answer_engine`-style duplication here either

The brief's file list also names `review_summary.py` and
`review_result.py` as separate modules under `agents/review/`.
**Decision:** both — `ReviewResult` and `format_review_summary` — live in
`domain/review.py` alongside `ReviewSession`, since all three are pure
data/formatting with the identical "belongs in `domain/`" reasoning
above; splitting them into separate files would be organizational
overhead with no capability behind the split. `review_storage.py` is
likewise not created as its own file: `SqliteReviewSessionStore` is added
directly into the existing single-file `storage/sqlite.py` convention
(`_connect` + a module-level `_XXX_SCHEMA`), the same convention every
other store in this project already uses (`SqliteApplicationStore`,
`SqliteResumeVariantStore`, `SqliteApplicationSessionStore`).

### `prepare` → `review`: the same handoff shape as `discover` → `apply`

`career-agent prepare` already builds an `ApplicationSession` and
persists it to SQLite (Phase 51). This phase adds one thing: `prepare`
also writes the session as a JSON file under `<artifacts_dir>/sessions/
<id>.json`, mirroring `discover`'s own "write opportunity-file handoffs
apply can consume" convention (ADR-0026) exactly. `career-agent review
--session <path>` is the consumer, the same relationship `apply` has to
`discover`. This is a genuinely new wiring decision, not a duplicate of
anything — `ApplicationSession` had no file-handoff path at all before
this phase.

### A near-miss avoided: no second `.prepare(`/`.submit(` collision

Phase 51 found and fixed one real collision between a method literally
named `prepare()` and the release-invariant test's literal `.prepare(`
ban (`test_no_external_submission_is_reachable_from_the_cli`, ADR-0054).
This phase's own new code (`ReviewEngine.review()`,
`run_review_command()`, `_write_application_session_handoff()`) was
checked against that same test before being considered done — none of it
collides, and the test's own suite (`tests/test_phase28_release_invariants.py`)
passes unchanged.

## What this phase explicitly does not do

No Submit, no browser click, anywhere — `ReviewEngine` cannot reach a
browser at all, structurally. No AI-based review — every decision is the
literal human answer, nothing inferred or summarized by a model. No
résumé/field editing — `ApplicationSession`'s content is read-only from
this phase's point of view; a rejected review's `next_action` names
`"revise_and_re_prepare"` as the only path forward, meaning re-running
`prepare`, not editing the stored session in place. No change to
`ApplicationPreparationEngine`, `ResumeVariantEngine`,
`ResumeTailoringPipeline`, or the execution-safety boundary. No
Submission Engine — `ReviewResult.next_action ==
"eligible_for_submission_engine"` is purely informational; nothing in
this codebase inspects it or calls anything further. That is explicitly
named, future, separate work (Phase 53), requiring its own explicit
authorization before any code is written that could click a real Submit
button.

## Consequences

- One new pure `domain/` module (`review.py`: `ApprovalStatus`,
  `ReviewSession`, `ReviewResult`, `format_review_summary`,
  `build_review_session`), automatically covered by the existing
  AST-based domain-purity test suite.
- One new package (`agents/review/`: `__init__.py`, `review_engine.py`).
- One new class in `storage/sqlite.py` (`SqliteReviewSessionStore`).
- `run_prepare_command` now also writes a JSON session-file handoff.
- One new `career-agent review --session <path>` CLI command.
- 36 new tests: 11 pure `domain/review.py` tests (summary formatting,
  construction, the no-duplication structural proof), 11 `ReviewEngine`
  tests (approve/reject/cancel/timeout, the two no-browser structural
  proofs), 7 `SqliteReviewSessionStore` tests, 7 real end-to-end CLI
  tests (`run_review_command` is fully offline — no LLM/network/browser
  — so it is tested directly, not just for file-loading). 947 total (up
  from 911).
- No new dependency, no version bump, no change to any existing safety
  semantics; `tests/test_phase28_release_invariants.py` passes unchanged.

## Future revisit criteria

Revisit when Phase 53 (Submission Engine) is explicitly authorized —
that is the point at which `ReviewResult.next_action ==
"eligible_for_submission_engine"` might become something real code
actually inspects, and the point at which "only Phase 53 may inspect
APPROVED" (this phase's own stated integration boundary) needs its first
real enforcement point designed. Revisit the CLI's indefinite-wait default
if real usage shows a bounded review-wait timeout is actually needed in
practice — the mechanism already exists and is tested; only the
production wiring is deferred.
