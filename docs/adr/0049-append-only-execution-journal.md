# ADR-0049: Append-only execution journal for `apply`/`auto` (Phase 23)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0048](0048-application-attempt-idempotency-guard.md)
  (`SqliteApplicationStore.prior_attempt_status()`, integrated with, not
  replaced by, this ADR), [ADR-0041](0041-scheduling-gates-and-bounded-auto.md)
  (`auto`'s structurally-cannot-submit guarantee, unchanged),
  [ADR-0037](0037-persistence-discover-and-first-profile-writer.md)
  (the SQLite store this journal lives alongside)

## Context: the central finding that reshapes this phase

Phase 23 asked "how can an interrupted autonomous run be reconstructed and
safely resumed without repeating irreversible external side effects,
bypassing confirmation, losing completed work, or falsely claiming
success?" -- and required a fresh repository-reality audit before any
design decision, explicitly warning against trusting the brief over what
the code actually does.

That audit found one fact that overrides most of the brief's assumed
shape: **`cli.py` -- the sole composition root -- never constructs or
calls any concrete `Applicator`.** Confirmed by grep: `TieredApplicator`,
`BrowserApplicator`, `EmailApplicator`, and `SubmissionPipeline` are never
imported by `cli.py` at all. `_apply_pipeline`'s own docstring and its
final printed message say so explicitly: *"Confirmed. No real ATS adapter
is wired in yet ... Nothing was actually sent."* `run_auto_command`'s
docstring makes the same guarantee structural (ADR-0041): no input
function, no `HumanConfirmation`, no `Applicator` anywhere in its call
graph.

**Consequence: the one class of operation Phase 23's brief is centrally
worried about -- an irreversible external submission (ATS API call,
browser form submit, email send) -- is structurally unreachable from any
real, runnable `career-agent` command today.** `TieredApplicator`/
`BrowserApplicator`/`EmailApplicator`/`SubmissionPipeline` exist and are
unit-tested against fakes (Playwright fakes, a fake `EmailDraftSink`), but
they are reachable only from tests, never from a live invocation. Every
crash-window scenario the brief asks about for a submit click, a browser
crash after submit, or an email send timeout is therefore a property of
already-built-but-unwired code, not of anything that can happen in
production right now.

This does not make Phase 23 pointless -- it changes what's actually
justified. Building a persisted, transition-gated recovery/resume system
around an irreversible external action that cannot currently occur would
be exactly the "infrastructure because it sounds sophisticated" mistake
this project's own discipline forbids. What the audit *did* find worth
closing:

- **No stable run identity exists anywhere** (`run_id`/`execution_id`:
  zero hits, confirmed by grep). A crashed `auto`/`apply` invocation
  leaves no queryable record of which invocation did what.
- **No reconstructable stage history exists.** The in-process event bus
  (`core/bus.py`) is explicitly documented as at-most-once and
  non-durable ("a crash loses in-flight events... SQLite remains the
  system of record, not the message path") -- by its own design, it was
  never meant to answer "what did the last run actually do."
- ADR-0048's idempotency guard (verified still present and unmodified:
  `prior_attempt_status()`, both refusal call sites) already protects the
  one real, reachable risk -- a duplicate `SqliteApplicationStore` row /
  duplicate human-confirmation prompt for the same opportunity across
  separate invocations -- but it only distinguishes "has *some* prior
  attempt," not "what exactly happened, in what order, this run."

## Decision

Add a minimal, persisted, append-only **execution journal**
(`SqliteRunJournal`, `storage/sqlite.py`; value types in the new pure
`domain/journal.py`) recording each `apply`/`auto` invocation's own stage
transitions under one fresh `run_id`, generated once per call
(`uuid.uuid4()`, matching every other identifier's construction pattern in
this codebase). This is Option C from the brief's own comparison
(append-only journal), chosen over:

- **Option A (no journal):** rejected -- it leaves `RQ8`/`RQ21` (stable
  run identity; reconstructability) genuinely unanswered, and the brief's
  own scope explicitly includes auditability, which the current in-memory
  event bus cannot provide across a crash.
- **Option B (mutable checkpoint row):** rejected -- overwriting a single
  row in place loses the ordered history a crash investigation actually
  needs (was TAILORING_STARTED reached before the crash, or did it get all
  the way to AWAITING_CONFIRMATION?); an append-only log costs one extra
  table and answers strictly more questions for the same complexity.
- **Option D (external workflow engine):** rejected outright -- nothing
  in this single-process, single-user, local, "tens of applications"
  repository justifies Kafka/Temporal/Celery/Redis/Kubernetes-class
  infrastructure, and the brief itself forbids reaching for it without
  overwhelming evidence, which does not exist here.

### Formal model

A run is identified only by `run_id` (a run identity, distinct from
`OpportunityKey` -- ADR-0014's `opportunity_id()`/`canonical_fingerprint()`
-- and distinct from `AttemptKey`, ADR-0048's `Application.id`/
`opportunity_id` pairing). This phase does not need an `ExternalEffectKey`
at all: there is no reachable external effect to key.

Each event:

```
J_i = (event_id, run_id, sequence_no, stage, event_type, outcome,
       attempt_no, occurred_at, metadata)
```

- **P1 (stable run_id):** one `uuid.uuid4()` generated once per
  `_apply_pipeline`/`run_auto_command` call, threaded through every event
  that call emits.
- **P2 (monotonic sequence):** `SqliteRunJournal.append()` computes
  `MAX(sequence_no) + 1` for that `run_id` and inserts inside the same
  connection -- proven by test, including that two different `run_id`s
  sequence independently.
- **P3 (durable before returning):** `sqlite3`'s `with connection:` block
  commits before `append()` returns; the caller never observes a
  "succeeded" `RunEvent` that wasn't actually persisted.
- **P4 (reconstructable in order):** `history(run_id)` reads `ORDER BY
  sequence_no`; `domain.journal.reconstruct_run()` folds that ordered
  list into a `RunState` (last stage/event_type/outcome, event count, a
  `completed` flag keyed only on the literal `event_type ==
  "RUN_COMPLETED"`).
- **P5 (replay of history has no side effect):** `history()`/
  `reconstruct_run()` are pure reads/pure functions -- proven by a test
  that reconstructing the same history twice yields an equal `RunState`.
- **P6 (append-only):** `SqliteRunJournal`'s only public methods are
  `append`/`history` -- proven by the same public-surface fidelity test
  this codebase already uses for `SqliteOpportunityRepository`. There is
  no update or delete method to remove.
- **P7 (fail-closed unknown transitions):** deliberately **not**
  implemented. `stage`/`event_type` are free-form, informational strings,
  not a validated transition table -- there is nothing in this codebase
  today that gates behavior on a transition being "valid," so building
  transition validation now would be speculative machinery protecting
  against a gate that doesn't exist. An unrecognized `event_type` folds
  into `RunState` exactly as given, never raises (tested).

### What this journal is for, and what it deliberately is not

It is for **reconstruction and auditability** of the two real, reachable
composition-root commands: "what did the last `career-agent apply`/`auto`
invocation actually do, in what order, before it stopped." It is **not**:

- a recovery planner (no `ρ(state, evidence) → decision` function is
  built): there is no automatic action to decide about, because nothing
  this journal observes is unsafe to simply re-run from the start.
  Re-running `apply`/`auto` after a crash today re-does discovery,
  ranking, and (for any opportunity not yet recorded) tailoring -- wasteful
  in LLM calls but not unsafe, and ADR-0048's guard already prevents
  re-recording/re-confirming an opportunity that got as far as
  `application_store.record()`.
- a `SUBMISSION_UNCERTAIN`/`EXTERNAL_ACTION_UNCERTAIN` state machine: no
  code path in `cli.py` can produce that ambiguity, since no code path
  calls a real `Applicator`. `TieredApplicator.submit()`,
  `BrowserApplicator.submit()`/`resume()`, and `EmailApplicator.submit()`
  each already return a definite `ApplicationSubmitted`/
  `ApplicationFailed`/`HumanActionRequired` (or raise a definite typed
  exception) within their own tested internal logic; what's genuinely
  missing is *durability of their in-memory `_pending`/`_paused` dicts*
  across a process restart -- but building that durability for code the
  composition root cannot yet reach would be exactly the "infrastructure
  in search of a problem" this project's discipline forbids.
- a formal `δ: S × E → S` transition function: not built, for the same
  reason as P7 above.

### The named, deferred trigger

**Before `TieredApplicator`/`BrowserApplicator`/`EmailApplicator`/
`SubmissionPipeline` are ever wired into a real `cli.py` command path**,
this journal must be extended to cover
`EXTERNAL_ACTION_STARTED`/`EXTERNAL_ACTION_CONFIRMED`/
`EXTERNAL_ACTION_UNCERTAIN`, `BrowserApplicator`'s in-memory
`_pending`/`_paused` state must gain real durability (or the pause must be
proven safe to simply lose), and a deterministic recovery planner
enforcing "`uncertain(action) ⇒ auto_replay(action) = false`" must exist
and gate that wiring -- tracked here explicitly so it is not silently
skipped when that day comes, not built speculatively now.

## Crash-window analysis (the operations that ARE reachable today)

For the real, reachable internal operations (file writes: resume
DOCX/PDF artifacts, ADR-0033, and discovery handoff JSON; SQLite writes:
`opportunities`/`applications`/`outcomes`/`run_journal`):

| Window | Operation | Classification |
|---|---|---|
| Crash before journal append | any stage | `RESOLVABLE_AUTOMATICALLY` -- nothing was recorded or attempted; a fresh invocation simply starts over |
| Crash after journal append, before the internal action it describes | any stage | `RESOLVABLE_AUTOMATICALLY` -- the internal action (tailoring, rendering, recording) is itself safely re-run from scratch; content-hash-addressed artifact filenames (ADR-0033) prevent a silent overwrite even if a partial file exists |
| Crash mid-`auto` loop (opportunity N of top_n) | per-opportunity tailor/gate/record | `RESOLVABLE_AUTOMATICALLY` -- a fresh `auto` invocation re-discovers, re-ranks, and ADR-0048's guard skips any opportunity already recorded; only un-recorded opportunities are retried |
| Crash after `application_store.record()`, before the human confirms via `apply` | `apply`'s confirmation step | `RESOLVABLE_AUTOMATICALLY` -- the handoff file and the recorded row both already exist; the human's next `apply` run reads the same file, ADR-0048 does not block it (status stays whatever `record()` wrote, and `apply` itself does not re-invoke the guard mid-flow) |
| Crash after a real external submission | N/A | `UNRESOLVED`, but **currently unreachable** -- no code path can cause this today; see the deferred trigger above |

No window above requires human review under the current, reachable
architecture -- because nothing currently reachable is irreversible.

## Consequences

- New pure module `domain/journal.py`: `RunEvent`, `RunState`,
  `reconstruct_run()`. Zero non-stdlib imports (domain-purity contract).
- `storage/sqlite.py`: new `_JOURNAL_SCHEMA` (`run_journal` table, unique
  index on `(run_id, sequence_no)`) and `SqliteRunJournal` (`append`,
  `history`).
- `cli.py`: `_apply_pipeline` and `run_auto_command` each accept an
  optional `run_journal: SqliteRunJournal | None`, emitting stage events
  (`RUN_STARTED`, `TAILORING_STARTED`/`COMPLETED`,
  `TRUTHFULNESS_APPROVED`, `AWAITING_CONFIRMATION`,
  `OPPORTUNITY_SKIPPED`/`APPLICATION_PREPARED`, `RUN_COMPLETED`, etc.)
  purely as an observer -- every existing return value, exit code, and
  printed message is unchanged; a test proves the happy path's exact
  event sequence, and a second proves ADR-0048's refusal path is itself
  a two-event, no-tailoring-attempted journal entry. `run_apply_command`/
  `run_auto_cli_command` construct a real `SqliteRunJournal` against the
  same `settings.database_path` already used for `SqliteApplicationStore`.
- Zero change to `ResumeTailoringPipeline`, the truthfulness gate, the
  ATS gate, any `Applicator`, confirmation/submission safety, ADR-0048's
  guard (verified still active by a dedicated restart test), or `auto`'s
  structurally-cannot-submit property.
- New tests: `tests/domain/test_journal.py` (pure reconstruction:
  determinism, repeat-read invariance, unrecognized-event tolerance),
  `tests/storage/test_run_journal.py` (public-surface fidelity,
  per-run monotonic/independent sequencing, ordered history, unknown
  `run_id`, metadata round-trip, close/reopen persistence, a redaction-
  shape check), plus integration tests in `test_cli_apply.py`/
  `test_cli_auto.py` (exact happy-path event sequence, the idempotency-
  refusal event sequence, and a two-invocation "restart" proving each
  gets its own `run_id` while ADR-0048 still prevents a duplicate
  application row).
- Zero cost, zero network, zero new dependency.
