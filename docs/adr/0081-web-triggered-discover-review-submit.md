# ADR-0081: Web-Triggered Discover, Review, and Submit

- **Status:** Accepted
- **Date:** 2026-07-12
- **References:** [ADR-0072](0072-web-dashboard-read-api.md) (the read-only
  dashboard API this phase extends, not replaces), [ADR-0074](0074-authentication-and-multi-user-platform.md)
  (per-user data ownership and the write-capable-router precedent this
  phase follows), [ADR-0070](0070-human-review-center.md) (`ReviewEngine`
  and its `input_fn` seam, reused unmodified), [ADR-0071](0071-human-approved-submission-engine.md)
  (the Submission Engine's fail-closed gate and human confirmation,
  unchanged), [ADR-0064](0064-job-search-preferences.md) (`JobPreferences`
  and `generate_search_queries`, reused unmodified), [ADR-0080](0080-browser-automation-robustness.md)
  (Phase 62's retry/diagnostics work, composed with here, not reopened)

## Context

Every prior dashboard phase (54, 56, 57, 58, 60) deliberately kept
Discover, Review, and Submit CLI-only: ADR-0072 states outright "no route
in this API can trigger discovery, tailoring, review approval, or
submission." That boundary was correct when it was drawn -- there was no
authentication, no per-user data model, no RBAC. All three now exist
(Phase 56/60). The dashboard has grown a real frontend, real accounts, and
real organizations, while its three most consequential workflows still
require dropping to a terminal.

The request driving this phase was explicit: **move the interface to the
web, not the business logic**. The dashboard must call the exact same
service layer the CLI already uses -- `ReviewEngine`,
`SubmissionEngine`, `build_discovery_sources`/`run_discover_command` --
never a reimplementation, and never a bypass of any existing safety gate
(human review, human confirmation, fail-closed execution, never-submit-
twice).

**A repository-reality audit (mandatory before any implementation) found:**

- `GET /api/reviews/pending`'s existing filter
  (`approval_status == "WAITING"`) has always returned an empty list in
  production. `ApprovalStatus`'s `WAITING` value is real in the type, but
  no code path in this codebase ever constructs a `ReviewSession` with
  it -- `ReviewEngine.review()` only ever returns
  APPROVED/REJECTED/CANCELLED/TIMEOUT. A genuine, pre-existing bug,
  directly on the path of making the Review Queue functional.
- `ReviewEngine.review()`'s `input_fn: Callable[[str], str] = input`
  seam was already designed for exactly this kind of reuse -- swapping
  `input()` for an HTTP-decision-returning closure needs zero changes to
  `ReviewEngine` itself.
- `SubmissionEngine.submit()`'s `confirm_fn: Callable[[], bool]` is
  called once, synchronously, for its blocking side effect; its return
  value was never even inspected. `SubmissionEngine.submit()`'s
  precondition/preflight checks (review-approved, artifact-integrity,
  the `domain/execution.py` fail-closed gate) all run *before*
  `confirm_fn` -- so a web caller reaching that point already knows the
  attempt would be allowed if confirmed, making an HTTP confirmation
  gate meaningful rather than decorative.
- `MasterProfile` has no per-user API store anywhere in this codebase --
  unlike `JobPreferences` (Phase 46/56's `SqliteUserPreferencesStore`),
  every CLI command defaults to `Path("profile.json")` in the current
  working directory, and the API layer has never read it.
- Write-capable routers in this codebase never live under the `/api/`
  prefix (enforced structurally by
  `tests/api/test_dashboard_api.py::test_dashboard_data_routes_are_get_only`,
  which asserts every `/api/*` route is GET-only) and mix
  GET/POST/PATCH/DELETE under one feature prefix (`notifications.py`,
  `team.py`) rather than splitting reads and writes across two prefixes.
- Only organization-scoped routers (`billing.py`, `organizations.py`,
  `team.py`) call `record_audit()`, which requires an `organization_id`;
  user-scoped-only mutating routers (`notifications.py`, `user.py`,
  `auth.py`, `coach.py`) do not.

## Decision

Three new/extended pieces of web surface, each calling the CLI's own
functions rather than reimplementing them, plus one real bug fix.

### 1. Discover: `POST /discover`

`build_discovery_sources(settings, preferences)` and
`run_discover_command(sources, repo, ...)` -- exactly what
`career-agent discover` calls -- run inside a FastAPI `BackgroundTasks`
job (a multi-source network fetch cannot honestly complete within one
HTTP request/response cycle). `run_discover_command` gains two optional,
additive observation hooks (`on_new_opportunity`, `on_source_error`,
both default `None`) so the API can build a status summary by observing
the same run rather than re-implementing source iteration/dedup --
every existing caller (the CLI, existing tests) keeps today's exact
behavior since the hooks are simply skipped when absent.

A new `DiscoveryRun` domain model (`domain/discovery_run.py`) and
`SqliteDiscoveryRunStore` (a real upsert, like `SqliteUserPreferencesStore`
-- a run's status genuinely changes in place, unlike the append-only
audit-trail stores) give the caller something to poll:
`POST /discover` returns a `PENDING` run immediately (HTTP 202);
`GET /discover/{run_id}` polls it; `GET /discover/runs` lists the
caller's own; `GET /discover/opportunities` (via a new
`SqliteOpportunityRepository.list_recent()`, `ORDER BY rowid DESC LIMIT
?` -- no schema migration needed, opportunities have no timestamp
column) lists the shared, deduplicated catalog for the Search Jobs page.
Search preferences are read from the caller's already-existing
`JobPreferences` (`GET`/`PUT /user/preferences`, Phase 56) -- no second
place to configure what a search looks for.

### 2. Review: the `WAITING` bug fix + `POST /reviews/decide`

`GET /reviews/pending` is redefined to what "pending" actually means: a
`READY_FOR_REVIEW` `ApplicationSession` with no `ReviewSession` recorded
for it yet -- returning the session itself (there is no review record to
return, by definition), not a `ReviewSession` filtered on a value that
never occurs. `POST /reviews/decide` calls `ReviewEngine().review(session,
input_fn=lambda _: "y" if approved else "n", notes=notes)` -- the exact
same class the CLI's `career-agent review` command uses, with only the
`input_fn` seam swapped. One decision per session is enforced (a second
`POST /reviews/decide` for an already-decided session is refused with
409), matching the CLI's own append-only `review_sessions` table
semantics. The whole `reviews.py` router moves off `/api/reviews` to
`/reviews` (mixed GET/POST, the "one feature, one prefix" precedent),
since it now has a real write action.

### 3. Submit: `POST /submissions/prepare` + `POST /submissions/{token}/confirm`

The riskiest piece, so it composes with `SubmissionEngine` rather than
rearchitecting it:

- **`SubmissionEngine.submit()`'s `confirm_fn`** now accepts a plain
  `bool` *or* an awaitable (checked via `inspect.isawaitable`, `await`ed
  if so). Every existing sync caller (`_default_confirm`,
  `_countdown_and_confirm`, every test fake) is unaffected -- a plain
  `bool` is never awaitable. The web path supplies an `async def
  confirm_fn()` that `await`s a bounded `asyncio.Future` (5-minute
  timeout), translating a timeout into `CancelledByUserError` --
  `SubmissionEngine.submit()`'s *existing* `except (KeyboardInterrupt,
  CancelledByUserError): return _finish(status="CANCELLED", ...)` needed
  zero new code. Silence can never imply "yes," the same discipline the
  CLI's countdown gate already holds.
- **`SubmissionEngine.submit()`/`_resolve_pause()`** gain
  `auto_close_on_pause: bool = False`. If the browser pauses for direct
  human interaction (a login wall, a challenge) *after* confirmation, the
  CLI's default behavior (block on a second `input()`, since a human is
  expected to resolve it on the visible browser window) is meaningless
  for a web caller with no visible browser to point anyone at yet (the
  Browser Automation Monitor, item 10 of the original request, is
  explicitly deferred -- see below). The web path passes
  `auto_close_on_pause=True`: the paused browser is closed and the
  attempt ends `UNKNOWN` with a warning telling the human to finish it
  via `career-agent submit`, rather than hanging a background task on
  stdin nobody can answer.
- **`cli.py::run_submit_command`'s core** (fresh re-tailor via
  `ResumeVariantEngine.build_materials()`, the promptfoo gate, then
  `SubmissionEngine.submit()`) is extracted into a new function,
  `submit_prepared_application(*, opportunity, profile, review,
  application_session, stored_variant, settings, confirm_fn,
  auto_close_on_pause=False)`, taking already-loaded domain objects
  instead of file paths. `run_submit_command` becomes a thin wrapper:
  load files, call `submit_prepared_application`, handle its new
  `SubmissionMaterialsError` (a refusal before any browser touch -- no
  LLM provider, promptfoo not passed, re-tailoring itself refused) the
  same way it already handled each of those failures inline. Two
  structural tests (`test_gates_before_constructing_the_live_verifier`,
  `test_no_application_session_check_precedes_llm_wiring`) moved with
  the logic they verify, re-asserting the exact same ordering guarantee
  against the function that now actually contains it.
- **`api/routers/submission_actions.py`** (`/submissions`, off `/api/`):
  `POST /submissions/prepare` starts a background task running
  `submit_prepared_application` and returns a token immediately (HTTP
  202). The pending entry (in-memory, module-level dict, never
  persisted -- the same reasoning `BrowserApplicator`'s own pause-token
  dict already relies on: each is tied to a live asyncio `Task` that
  cannot survive a process restart anyway) tracks
  `PREPARING -> AWAITING_CONFIRMATION -> SUBMITTING -> DONE|FAILED`.
  `POST /submissions/{token}/confirm` resolves the same `asyncio.Future`
  the background task's `confirm_fn` is blocked awaiting -- declining,
  confirming twice, or confirming a token that isn't currently
  `AWAITING_CONFIRMATION` are all refused (404/409), never silently
  re-triggering anything. Both `prepare_submission` and
  `confirm_submission` are declared `async def` deliberately: FastAPI
  runs `async def` routes directly on the main event loop (the same loop
  the background task runs on), so the `Future` is only ever touched
  from one thread -- a plain `def` route would run in a worker thread
  pool instead, making it thread-unsafe.
- `MasterProfile` is loaded from the same `Path("profile.json")` default
  every CLI command already uses -- no new per-user profile store
  invented. This is a deliberate continuation of this project's
  single-operator profile framing (ADR-0000/ADR-0078: "the CLI remains
  single-operator with no organization awareness"), not an oversight:
  `MasterProfile` represents "the person applying," a genuinely singular
  concept for a self-hosted install, unlike `JobPreferences` (which
  legitimately varies per dashboard account).

### Router wiring

`discover`, `reviews` (moved), and `submission_actions` join the
write-capable router group in `api/app.py`, following the established
`/api/` = read-only, feature-prefix = mixed-methods convention. None of
the three calls `record_audit()` -- matching the existing precedent that
only organization-scoped routers do, and these actions were never
organization-scoped historically (Phase 60 made the same call for the
9 pre-existing personal-resource tables).

### Frontend

Shipped in this same phase, not deferred: Search Jobs is a real filter
form bound to Job Search Preferences (`PUT /user/preferences`, already
existing but previously unused by any page), with a Search button that
saves preferences then triggers a run, a polled status callout, and a
real results list. Review Queue's `usePendingReviews()` now returns
`ApplicationSession[]` directly (matching the backend fix) -- no join
needed, since a pending item *is* the session -- with an inline
Approve/Reject-then-confirm step before deciding. Submission Queue's
Submit starts a prepare attempt, polls its status, and shows a real
Confirm/Cancel step once `AWAITING_CONFIRMATION` is reached.
`lib/derive.ts`'s `joinReviewsWithSessions` (Phase 55) was removed as
genuinely dead code once Review Queue stopped needing it.
`CliOnlyAction` still names exactly one workflow: `career-agent prepare`
(tailoring), the one explicitly deferred above.

## Alternatives considered

- **Reimplement discover/review/submit logic natively in the API
  routers.** Rejected outright -- this is exactly the duplication the
  driving request explicitly forbade, and it would let the CLI and web
  paths drift apart on safety-critical behavior (never-submit-twice,
  the truthfulness gate, artifact-integrity checking) over time.
- **A single synchronous `POST /submissions/submit` that blocks until
  done.** Rejected: the CLI's own countdown-then-ENTER gate is
  deliberately a real wait for a human decision, which cannot be a
  single blocking HTTP request without either a very long-held
  connection (fragile, timeout-prone) or silently skipping the human
  gate (unacceptable). The two-step prepare/confirm split is the direct
  HTTP analogue of the CLI's two-phase confirm flow.
- **A full live-browser monitor so the web path can resolve a pause
  interactively.** Named as its own future phase (item 10 of the
  original request) rather than solved partially here -- it needs a
  genuinely new capability (streaming the browser's state to the
  dashboard) this phase's scope did not include. `auto_close_on_pause`
  is the honest interim: a pause becomes a clear, visible `UNKNOWN`
  with a next step, never a silent hang.

## Consequences

- Search Jobs, the Review Queue, and the Submission Queue are now real,
  authenticated, web-triggered workflows -- calling the identical
  `build_discovery_sources`/`run_discover_command`, `ReviewEngine`, and
  `submit_prepared_application`/`SubmissionEngine` the CLI uses. Every
  existing safety gate (human review, human confirmation, fail-closed
  execution, never-submit-twice) is unchanged and unbypassable from the
  new routes -- verified by running the full pre-existing
  `test_submission_engine.py`/`test_cli_submit.py`/`test_cli_discover.py`
  suites unmodified except for the two structural-test relocations noted
  above.
- `GET /reviews/pending` (formerly `GET /api/reviews/pending`) now
  actually returns something when there is something pending -- a real
  bug fix, not just new surface.
- A submission attempt that pauses for a login wall or challenge now
  fails visibly (`UNKNOWN`, closed browser, clear message) from the web
  path instead of hanging a background task indefinitely.
- `career-agent serve`'s help text and this project's dashboard-API
  description no longer claim discover/review/submit are CLI-only --
  they are not, as of this phase.

## Deferred, not silently skipped

- **Analytics overhaul, Interview Tracking, Email Integration, Calendar
  Integration, Kanban Application Pipeline, Browser Automation Monitor**
  (items 4-7, 9-10 of the original request). Each is a substantial,
  separate feature area -- several requiring genuinely new external
  integrations (Gmail AI classification, Calendar APIs) -- deserving
  their own repository-reality audit, not folded into this already-large
  phase.
- **"Prepare Resume"/"Generate Cover Letter" buttons in the Search Jobs
  results.** `ApplicationPreparationEngine` (`career-agent prepare`) is
  itself a substantial CLI-to-API migration with its own real headed-
  browser complexity, deserving its own future audit -- not attempted
  here. The dashboard shows an honest "Prepare via CLI" hint instead of
  fabricating a button that does nothing real.
- **Resolving a browser pause from the dashboard.** Needs the Browser
  Automation Monitor (deferred above); `auto_close_on_pause=True` is the
  honest interim behavior in the meantime.
- **A configurable confirmation timeout.** Fixed at 5 minutes in code,
  not exposed as a setting -- no evidence yet a different value is
  needed.

## Future revisit criteria

- If Phase 64+'s Browser Automation Monitor ships, `auto_close_on_pause`
  should be revisited: a web caller could then resolve a pause
  interactively instead of always closing the browser.
- If this project ever moves beyond a single-operator `MasterProfile`
  (multiple dashboard accounts each needing their own résumé profile),
  `Path("profile.json")` needs a real per-user store, mirroring
  `SqliteUserPreferencesStore`.
- If the in-memory pending-submission registry's assumption (single
  process, no restart mid-flow) stops holding -- e.g. a future
  horizontally-scaled deployment -- it needs a durable, cross-process
  design instead.
