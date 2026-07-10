# ADR-0058: Declined-confirmation lifecycle and retry semantics (Phase 36)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0048 (application-attempt idempotency guard), ADR-0049
  (append-only execution journal), ADR-0050 (execution-safety boundary),
  ADR-0056 (v1.0 prepare-only scope), ADR-0057 (CI and cross-platform
  hardening)

## Context

Phase 36 ran the first genuinely controlled live-Groq validation of the
prepare-only pipeline, on the user's real Windows machine with a real
`GROQ_API_KEY` and a real `verify-promptfoo --provider groq` PASS. The live
run succeeded end-to-end: profile loaded, real Groq-backed tailoring, ATS
score `78.125`, `truthfulness_approved = 1`, DOCX rendered, confirmation
prompt reached. The user answered `N`.

The CLI printed the correct message ("Not confirmed. Exiting without
submitting.") and the append-only run journal correctly recorded the run's
final event as `RUN_COMPLETED outcome=declined`. **The application-store
row, however, was recorded with `status = "pending"`** — the same status a
row gets when tailoring succeeds, regardless of what confirmation later
decides. Running `apply` again for the same opportunity was then refused:

> Refusing to tailor: opportunity 'phase36-jd-junior-backend' already has a
> recorded application attempt with status 'pending'. Applying again could
> create a duplicate real-world submission...

This message is not accurate for this run: no submission was ever attempted
or even reachable (ADR-0050, `executor_available=False`, hardcoded). The
declined run and the append-only journal both already knew this; only the
application-store row did not.

## Root cause (reproduced offline, no live call needed)

`_apply_pipeline` (`cli.py`) called `application_store.record(...)` **once,
unconditionally, immediately after `pipeline.run()` returned** — before the
truthfulness-rejection check, and long before the confirmation prompt is
even shown. The `Application.status` value baked into that one row
(`"pending"` if truthfulness approved the draft, `"rejected"` otherwise,
set inside `ResumeTailoringPipeline`) can therefore never reflect what
confirmation later decides, because confirmation hasn't happened yet when
the row is written. There was no second write path to correct it
afterward — `SqliteApplicationStore.record()` is `INSERT OR IGNORE`
(append-only by design, never overwrites), so the row was permanently
stuck at `"pending"`.

`prior_attempt_status()` (ADR-0048) then correctly did its job on stale
information: it blocks a retry for any status other than `"rejected"`,
and `"pending"` is one of the statuses that is *supposed* to mean "a real
submission may have been attempted, don't touch this automatically." For a
declined run, that meaning is simply wrong.

Reproduced deterministically offline in
`tests/test_cli_apply.py::test_declined_confirmation_does_not_permanently_block_retry`
(fails on the pre-fix code with fakes only — no network, no LLM, no API
key) before any production code changed, per this phase's reproduction-first
requirement.

## Decision

**Option F (minimal ordering + status semantic fix).** No new subsystem, no
state machine, no schema migration.

1. **`Application.status` gains one new literal value: `"declined"`.** It
   means exactly what `"rejected"` already means for idempotency purposes:
   *this attempt produced zero external side effect.* No `CHECK` constraint
   exists on the `status` column (`TEXT NOT NULL`), so this is fully
   backward-compatible with every existing database -- no migration.
2. **`_apply_pipeline` now records exactly once per run, only once this
   run's true terminal status is known**, instead of once, unconditionally,
   before confirmation:
   - truthfulness-rejected → recorded with `status="rejected"` (unchanged
     meaning, only the call site moved into that branch);
   - confirmation declined → recorded with `status="declined"` (**new** —
     a copy of the pipeline's `Application` with `status` overridden via
     `model_copy(update=...)`, never mutating a previously-written row);
   - confirmed (execution boundary refuses, as it always does today) →
     recorded with `status="pending"` (unchanged).

   Every terminal branch still writes exactly one row; the audit trail used
   by `report`/`export` (ADR-0039, Phase 15's funnel counts, which read
   status generically and do not special-case any particular value) is
   unaffected and, for the rejected/declined paths, more accurate than
   before.
3. **`prior_attempt_status()` excludes `"declined"` from the blocking set**,
   the same way it already excludes `"rejected"`, with the same
   justification restated for both together. `"pending"`,
   `"paused_for_human"`, `"submitted"`, and `"failed"` are unchanged and
   remain fully blocking — a genuinely risky prior attempt is never made
   retryable by this change.

## Why other options were rejected

- **Option A (no change)** was rejected: this is not documented, intended
  policy — ADR-0048 explicitly says a second attempt "must be a human
  decision, never automatic," and the human *already made that decision*
  by typing `N`. Requiring a *second*, separate human act (manual SQLite
  surgery) to un-stick the opportunity contradicts that stated intent, and
  the refusal message actively asserts a real-world-submission risk that
  provably does not exist for this exact case.
- **Option B (move all persistence to after confirmation)** was rejected:
  the rejected-draft branch's row is written for the `report`/`export`
  funnel counts (Phase 15/ADR-0039) and must stay recorded at rejection
  time, not deferred past a confirmation prompt it never reaches.
- **Option D (derive effective status from the journal at read time)** was
  rejected: it would make `prior_attempt_status()` depend on cross-store
  joins against the journal on every call, coupling two stores that are
  deliberately independent (ADR-0049: the journal is "purely for
  reconstruction/auditability, never a gate"). Recording the correct
  status once, at the store that already gates, is simpler and keeps that
  separation intact.
- **Option E (append a separate lifecycle-event table)** was rejected as
  unjustified sophistication for a single new terminal state, consistent
  with ADR-0048's own stated discipline against building a richer state
  machine without evidence a bigger model is needed.

## Safety invariants preserved

No safety-relevant behavior changed. External submission remains
**UNREACHABLE** (no `Applicator` construction, `executor_available=False`
hardcoded, ADR-0050 unchanged). Genuinely risky statuses
(`pending`/`paused_for_human`/`submitted`/`failed`) remain fully
retry-blocking (`tests/storage/test_sqlite_store.py::test_prior_attempt_status_still_blocks_on_genuinely_risky_statuses`).
The run journal remains append-only and untouched by this change. No
truthfulness, ATS, or Promptfoo semantics changed. No prompt version
changed. No dependency changed.

## Consequences

- Changed: `src/career_agent/domain/models.py` (`Application.status` gains
  `"declined"`), `src/career_agent/storage/sqlite.py`
  (`prior_attempt_status()` excludes `"declined"` alongside `"rejected"`),
  `src/career_agent/cli.py` (`_apply_pipeline` records once per run, at the
  correct terminal branch, via a small internal `_record` helper).
- New tests (4): the Phase-36 reproduction regression
  (`test_declined_confirmation_does_not_permanently_block_retry`), a
  rejected-path recording regression
  (`test_rejected_draft_is_recorded_and_does_not_block_retry`), and two
  storage-layer unit tests (`test_prior_attempt_status_ignores_declined_attempts`,
  `test_prior_attempt_status_still_blocks_on_genuinely_risky_statuses`).
- No schema migration, no new dependency, no prompt-version change, no
  Promptfoo artifact change, no external-submission reachability change.

## Future revisit criteria

Revisit if a real executor is ever wired (ADR-0050's premise changes,
requiring a full re-audit of every status's meaning); if `auto` ever grows
its own confirmation path (today it structurally cannot confirm, ADR-0041);
or if evidence emerges that a richer execution state machine is actually
needed (the same bar ADR-0048 already set and this ADR does not lower).
