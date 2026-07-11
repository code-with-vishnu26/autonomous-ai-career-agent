# ADR-0071: Human-Approved Submission Engine — wiring the executor ADR-0050 named and deferred

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0050](0050-execution-safety-boundary.md) (the
  fail-closed execution-safety boundary this phase finally wires a real
  executor through — `domain/execution.py`'s own docstring named this
  exact moment as its trigger), [ADR-0020](0020-browser-tier-session-and-pause.md)/[ADR-0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md)/[ADR-0032](0032-question-answerer-wiring.md)
  (`BrowserApplicator`, the real Tier-2 executor this phase reuses
  unmodified), [ADR-0018](0018-submission-safety.md) (`HumanConfirmation`'s
  token-binding, reused unchanged for the final click), [ADR-0054](0054-production-readiness-release-gate.md)
  (the release-invariant contract this phase deliberately, explicitly
  updates — not weakens), [ADR-0069](0069-application-preparation-engine.md)/[ADR-0070](0070-human-review-center.md)
  (`ApplicationSession`/`ReviewSession`, the inputs this phase consumes)

## Context

Every phase since Phase 24 (ADR-0050) has built toward, and explicitly
refused to cross, one boundary: an external, irreversible submission.
`domain/execution.py`'s own docstring names the trigger for crossing it
precisely: *"a future phase wiring a real executor cannot do so without
satisfying every condition here."* Phase 53 is that phase — undertaken
only after the user's own explicit, detailed, safety-first authorization
(multiple confirmation gates, fail-closed preconditions, no CAPTCHA/MFA
automation, no password storage, `FeatureUnavailableError` over guessed
provider support).

The audit found the actual browser-driving executor already exists,
fully built and tested, and has been sitting unwired specifically pending
this boundary: `agents/apply/browser_applicator.py::BrowserApplicator`
(Tier 2, ADR-0020/0028/0032) already does fill → triage/auto-answer →
click submit → check for a challenge → return `ApplicationSubmitted`, as
one continuous, real, Playwright-driven browser session. **This phase
does not build a second implementation of any of that.** It builds the
fail-closed gate in front of it that has been the one missing piece since
Phase 24.

## Decision

### `SubmissionEngine` gates; `BrowserApplicator` executes

`agents/submission/submission_engine.py::SubmissionEngine.submit()`
constructs a fresh `BrowserApplicator` (session-store-keyed by opportunity
id, exactly as it already was designed) and calls its existing, unmodified
`prepare()`/`submit()`/`resume()` — **only after every one of the
following holds, checked in this exact order, fail-closed at each step**:

1. `review_session.application_session_id == application_session.id`
   (the two files actually pair together — refuses
   `"review_application_mismatch"` otherwise, catching a mismatched pair
   of handoff files before anything else is even considered).
2. `review_session.approval_status == "APPROVED"` (refuses
   `"review_not_approved"` — `REJECTED`/`CANCELLED`/`TIMEOUT`/`WAITING`
   all refuse identically here).
3. `application_session.status == "READY_FOR_REVIEW"` (refuses
   `"application_not_ready"`).
4. **Artifact integrity**: the freshly re-tailored `SubmittableApplication`
   (built by the caller via `ResumeVariantEngine.build_materials()`, the
   *exact* same call `prepare` originally made) must equal, content-for-
   content, the `ResumeVariant` stored at prepare-time
   (`SqliteResumeVariantStore.get(application_session.resume_variant_id)`,
   a new lookup-by-id method added to that existing store). A profile
   edit between `prepare` and `submit` fails this check — the resume
   about to be submitted is proven to be the one that was actually
   reviewed, never assumed.
5. **The execution-safety boundary itself**
   (`domain.execution.execute_allowed`, unmodified): `source_policy`
   (`resolve_source_policy`, unmodified — Greenhouse/Lever/Ashby resolve
   `ASSISTED`; everything else, including every job-board/Workday source
   this codebase has no assisted flow for, resolves `MANUAL_ONLY`/
   `UNKNOWN` and refuses here); `executor_available=True` (the one field
   this phase is finally allowed to set); `artifact_matches` (step 4);
   `prior_outcome` (from `SqliteSubmissionResultStore`, new this phase —
   a prior `SUBMITTED`/`UNKNOWN`/`ABORTED` result for this opportunity
   refuses a retry, unconditionally, the same
   `_RETRY_UNSAFE_PRIOR`/`OUTCOME_UNCERTAIN` guarantee ADR-0050 already
   proved exhaustively).

This is evaluated as a **dry run with `confirmation_present=True`**
*before* ever asking the human anything — so a doomed attempt (wrong
source, stale content, unsafe retry) is refused immediately, and the
human is never asked to sit through a countdown for something that was
always going to fail.

### The final human gate is real, and un-bypassable

Only once every condition above holds does `_countdown_and_confirm`
(`cli.py`) run: a 5-second visible countdown, then a **blocking**
`input()` call. `SubmissionEngine.submit()` calls this through an
injectable `confirm_fn: Callable[[], bool]` — production code path always
actually calls it; there is no code path that proceeds to
`BrowserApplicator.prepare()` without `confirm_fn()` having genuinely
returned. `KeyboardInterrupt` during the wait is caught and recorded as
`CANCELLED`, distinct from every refusal reason above (a refusal means a
precondition failed; a cancellation means every precondition held and the
human still said no at the last second).

### Verification: no fabricated confirmation, ever

`SubmissionResult.confirmation_id`/`confirmation_url` are **never**
populated. This project has never verified a "Thank you" banner, a
confirmation-number field, or a success redirect against a real, live
posting on *any* platform — the identical discipline that already kept
`LeverFormFiller`/`AshbyFormFiller` honest about unverified selectors
(ADR-0028) and kept `SessionManager`'s login detection caller-supplied
rather than platform-guessed (Phase 47). The only verified success signal
this codebase has ever established is `BrowserApplicator`'s own event
distinction: `ApplicationSubmitted` (submit was clicked, no challenge
visible afterward) vs. `HumanActionRequired` (a pause). `SubmissionResult`
reuses that distinction unchanged and records an explicit warning
explaining why no confirmation id/receipt was extracted, rather than
guessing at one.

A `HumanActionRequired` pause (a live-DOM challenge, or a required field
`BrowserApplicator`'s Phase A triage could not auto-resolve) gets exactly
**one** resume attempt: the human is told to resolve it directly on the
visible browser window, then presses ENTER once, and
`applicator.resume()` (unmodified) is called once. If still unresolved,
the result is `UNKNOWN` — never silently retried, never guessed into
`SUBMITTED` or `FAILED`.

### `FAILED` vs. `UNKNOWN`: the exact same discipline as `AckClass.AMBIGUOUS`

`UnsupportedFormFieldsError`/`MissingResumeArtifactError` are raised
*before* any click (verified by reading `BrowserApplicator.submit()`'s
own control flow: fill/triage happens entirely inside a block that closes
the browser and re-raises before the click is ever reached) — safe to
record as `FAILED` (a definite non-submission). **Any other exception**
raised anywhere inside the `applicator.submit()` call — which also
contains the actual click — does **not** prove the click never fired, so
it is recorded as `UNKNOWN`, never `FAILED`. This is the identical
"ambiguous evidence can never become a definite result" rule
`domain.execution.outcome_from_ack` already enforces for `AckClass.
AMBIGUOUS → OUTCOME_UNCERTAIN` — applied here to the analogous exception-
handling decision, not re-derived from scratch.

### No new `verification.py`/`tracker.py`

The brief's file list names five modules under `agents/submission/`.
**Decision:** `submission_result.py`/`submission_session.py` collapse
into `domain/submission.py` (`SubmissionResult`, pure data), the same
precedent Phases 50-52 already set for pure results living in `domain/`.
`verification.py` is not built as a separate module because there is no
separate verification *algorithm* — see above, verification **is**
`BrowserApplicator`'s existing event distinction, reused, not
reimplemented. `tracker.py` is not built either: `SqliteSubmissionResultStore`
joins the existing one-file `storage/sqlite.py` convention (`_connect` +
a module-level `_XXX_SCHEMA`), the same convention every other store in
this project already uses, and `storage/excel.py` gains a small
`export_submissions()` sibling function (same `Workbook`-writing style as
`export_applications`) rather than a bespoke tracker.

### A found, deliberate change: the release-invariant test

`tests/test_phase28_release_invariants.py::test_no_external_submission_is_reachable_from_the_cli`
(ADR-0054) asserted, as a blanket literal-substring ban, that `.submit(`
and `.prepare(` never appear in `cli.py`'s source at all — true and
correct through Phase 52, when *no* submission was reachable from
anywhere. `run_submit_command`'s own `engine.submit(...)` call trips that
literal ban directly. **This is not a false positive to patch around —
it is the test correctly detecting the exact thing this phase is
authorized to change.** The test is renamed and rewritten (not deleted,
not weakened) to `test_only_the_submission_engine_can_reach_a_real_executor`:
it still forbids `TieredApplicator(`/`EmailApplicator(`/`SubmissionPipeline(`
(Tier 1 direct-API and email remain fully dead — this phase only wires
the browser tier) and still forbids `BrowserApplicator(` *directly in
`cli.py`* (it is only ever constructed inside `SubmissionEngine` — a
future edit that bypasses the engine and constructs it directly in
`cli.py` would still trip this), and adds a new, stronger, positive
assertion: `execute_allowed(` must appear, and must appear *before*
`applicator.submit(` textually, inside `submission_engine.py` itself —
proving the fail-closed gate genuinely runs in front of the real call,
not merely that some safety-sounding code exists somewhere in the file.

## What this phase explicitly does not do

No CAPTCHA/MFA solving (a live pause still requires a human, exactly as
`BrowserApplicator` already required). No password storage (nothing in
this phase touches a credential; `EncryptedSessionStore` is reused
unchanged). No silent retry (`prior_outcome` unconditionally refuses a
repeat after `SUBMITTED`/`UNKNOWN`/`ABORTED`). No AI-based verification
(the only verification signal is `BrowserApplicator`'s own deterministic
event). No résumé/content editing at submit time (the artifact-integrity
check exists specifically to *refuse* a mismatch, never to silently
proceed with different content). No change to `BrowserApplicator`,
`TieredApplicator`, `EmailApplicator`, `ResumeTailoringPipeline`,
`ApplicationPreparationEngine`, or `ReviewEngine` — this phase adds a
gate and a caller, zero lines of any existing safety-critical class
changed.

## Consequences

- One new pure `domain/` module (`submission.py`: `SubmissionStatus`,
  `SubmissionResult`).
- One new package (`agents/submission/`: `__init__.py`,
  `submission_engine.py`).
- One new class in `storage/sqlite.py` (`SqliteSubmissionResultStore`)
  plus a `get(id)` method added to the existing `SqliteResumeVariantStore`
  (needed for the artifact-integrity check).
- `run_review_command` now also writes a JSON review-session handoff
  (mirroring `prepare`'s existing `ApplicationSession` handoff exactly),
  consumed by the new `career-agent submit --review-session ...
  --opportunity-file ... --profile ...` command.
- One deliberately, explicitly rewritten release-invariant test (not
  weakened — made stronger and more precise for the new reality).
- 27 new tests (974 total): 3 pure `SubmissionResult` tests, 6
  `SqliteSubmissionResultStore` tests, 11 `SubmissionEngine` tests (9
  fail-closed precondition tests that run with or without a local
  Chromium build, plus 2 real-Chromium tests proving an actual click only
  happens once every gate holds, and that Ashby's stub correctly
  surfaces as `FeatureUnavailableError`), 7 CLI file-loading/gate-ordering
  tests (`run_submit_command`'s live-provider path is untestable in this
  sandbox, disclosed the same way `run_apply_command`'s already is).
- No new dependency, no version bump, no change to any other safety
  semantics; the full existing suite (974 tests) passes unchanged
  alongside the new coverage.

## Future revisit criteria

Revisit `_resolve_pause`'s reach into `BrowserApplicator`'s private
`_paused` dict (needed because `HumanActionRequired` carries no
`pause_token` field of its own — the same private-attribute reach this
project's own test suite already uses, just now in production code for
the first time) if a future phase adds a `pause_token` field to that
event; that is a Tier-2 event-schema change out of scope here. Revisit
`export_submissions()`'s standalone-sheet shape if a future phase wants a
single combined applications+submissions Excel export rather than two
separate sheets/files. Revisit the countdown's fixed 5-second duration if
real usage shows a different value is warranted — it is a plain
parameter, not a hardcoded constant buried in logic.
