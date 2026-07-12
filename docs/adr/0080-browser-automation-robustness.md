# ADR-0080: Browser Automation Robustness

- **Status:** Accepted
- **Date:** 2026-07-12
- **References:** [ADR-0065](0065-browser-automation-foundation.md) (the
  `integrations/browser` foundation layer and its zero-domain-knowledge
  contract, enforced by `tests/integrations/test_browser_purity.py`),
  [ADR-0048](0048-application-attempt-idempotency-guard.md)/[ADR-0050](0050-execution-safety-boundary.md)
  (the existing never-submit-twice guarantees this phase reaffirms and
  never touches), [ADR-0071](0071-human-approved-submission-engine.md)
  (the Submission Engine's fail-closed gate and un-bypassable human
  confirmation, unchanged), [ADR-0079](0079-production-hardening.md)
  (Phase 61, the prior hardening pass this phase continues in the same
  spirit -- observability/reliability, not new feature surface)

## Context

With the roadmap feature-complete and Phase 61 (production hardening)
shipped, the next hardening target is browser automation -- the part of
this project most likely to fail silently against a real, live ATS
posting, since it has never been exercised against one in this codebase's
history.

**A repository-reality audit (mandatory before any implementation) found:**

- **No retry logic anywhere.** `agents/planner/execution_plan.py`
  declares `max_retries: int = 0` as plan metadata only -- its own
  docstring says it is "not enforced ... anywhere in this codebase." No
  Playwright action retries on a transient failure (a flaky selector, a
  slow navigation).
- **No failure capture anywhere.** No screenshot, no page-HTML dump, no
  console-log capture exists in `integrations/` or `agents/`.
- **No crash/session recovery.** `BrowserApplicator.submit()`'s only
  failure handling was `except BaseException: await browser.close();
  raise` around the pre-click fill step -- guaranteed cleanup, nothing
  more. `_click_submit_and_check_challenge()` and `resume()`'s two
  click-completing paths had **no** exception handling at all: a failure
  there left the browser open and unclosed, propagating uncaught all the
  way to the CLI.
- **Never-submit-twice is already real and settled**, at two layers:
  `domain/execution.py`'s `execute_allowed()` refuses on
  `DEFINITELY_SUBMITTED`/`OUTCOME_UNCERTAIN` prior outcomes (ADR-0050),
  and `SqliteApplicationStore.prior_attempt_status()` is checked by the
  CLI before tailoring even starts (ADR-0048). **Not reopened or
  duplicated by this phase** -- any retry logic here must compose with,
  never route around, these guarantees.
- **Headed-by-design, confirmed still deliberate.** `BrowserManager`
  defaults to `headless=False`; ADR-0076 already named making it work
  headlessly in Docker as out-of-scope, separate future work. This phase
  doesn't change that -- real-browser tests here use the same
  `headless=True`-in-tests / `skipif no local Chromium` pattern every
  other browser test in this repository already uses, proving the code
  for real rather than mocking Playwright away.

## Decision

Three real, scoped additions -- no rewrite of `BrowserApplicator`'s
existing pause/resume/challenge/refusal logic, no change to what gets
submitted or when.

### 1. Bounded retry for transient, pre-submit actions only

`integrations/browser/retry.py` (new): `retry_async()`, a small
generic bounded-retry helper (exponential backoff, no new dependency --
the same "one small helper beats pulling in `tenacity`" precedent
`core/logging_config.py`'s `JsonFormatter` already established).
Deliberately narrow about *what* it wraps: `_open_page`'s `page.goto()`
call and `submit()`'s `filler.fill_identity_and_resume()` call are
retried (up to 3 attempts) on `playwright.async_api.TimeoutError` only.
**The submit click itself (`_click_submit_and_check_challenge`) is never
wrapped in retry** -- retrying a click risks a second real-world
submission if the first attempt actually succeeded but the response was
slow, which is exactly the ambiguity `domain/execution.py`'s
never-submit-twice guarantee exists to prevent. `retry_async`'s own
docstring states this constraint directly so a future caller can't wrap
the click by mistake without reading why not to.

### 2. Failure-diagnostics capture (screenshot + HTML + console log)

`integrations/browser/diagnostics.py` (new): `ConsoleLogCollector`
(attached to every page `_open_page` creates, bounded to the last 500
lines) and `capture_failure_diagnostics()` (screenshot, `page.content()`,
and the collected console log, written to
`<diagnostics_dir>/<correlation_id>_<timestamp>/`). Best-effort by
construction -- every individual capture step swallows its own
exceptions (a page that's already closed still lets the other two
artifacts attempt to write) and the whole function returns `None` rather
than raising if even the directory can't be created. A failure while
diagnosing a failure must never mask or replace the real exception.

Wired into `BrowserApplicator` via a new `_fail_with_diagnostics()`
helper, called from three places that previously had no exception
handling at all or only closed-and-reraised: the pre-click fill/triage
step (`submit()`), the submit-click step (`submit()`, previously
**unguarded** -- a real gap this phase closes), and both of `resume()`'s
click-completing paths (also previously unguarded). Every one of these
now: captures diagnostics if `diagnostics_dir` was configured, closes the
browser, and re-raises the *original* exception unchanged, with only one
new attribute (`exc.diagnostics_dir`) added to it. `diagnostics_dir`
defaults to `None` (capture disabled) -- every existing caller/test that
never passes it keeps today's exact behavior; `SubmissionEngine`/CLI wire
`Path(settings.artifacts_dir) / "browser_failures"` through by default.

`domain/submission.py`'s `SubmissionResult` gains one new, optional field
(`diagnostics_dir: str | None = None`) -- additive, never populated on
`SUBMITTED`/`REFUSED`/`CANCELLED` (a refusal never touches a browser; a
success needs no diagnosis), read off the caught exception's
`diagnostics_dir` attribute in `SubmissionEngine.submit()`'s two
`except` blocks and the newly-added catch-all in `_resolve_pause()`
(same "an exception during `resume()` doesn't prove the click never
fired, so it's `UNKNOWN`, never `FAILED`" reasoning `submit()`'s own
outer `except Exception` already uses).

### 3. `resume()`'s missing exception handling

Not originally scoped, found while implementing #2: `resume()`'s two
click-completing paths had zero exception handling before this phase --
a failure there left the browser open, unclosed, and propagated all the
way out of `SubmissionEngine.submit()` uncaught (since `_resolve_pause()`
only ever caught `ChallengeStillPresentError`/
`RequiredFieldsStillUnresolvedError`, not a generic failure). Fixed
alongside #2, using the same `_fail_with_diagnostics()` helper, with a
matching `except Exception` added to `_resolve_pause()` mirroring
`submit()`'s own `UNKNOWN`-on-ambiguous-evidence handling exactly.

## Consequences

- A transient Playwright timeout during navigation or form-filling no
  longer fails an entire submission attempt outright -- it retries up to
  3 times before giving up, verified against a real Chromium instance
  with a form filler that fails twice then succeeds (proving the retry
  loop actually recovers, not just that the code compiles).
- Every browser-action failure that reaches `BrowserApplicator`, with
  `diagnostics_dir` configured, now leaves a screenshot, the page's HTML,
  and its console log on disk -- verified end-to-end through
  `SubmissionEngine.submit()`, not only at the lower `BrowserApplicator`
  layer.
- A submit-click or resume-click failure now always closes the browser
  before propagating -- previously it did not, a real resource-leak gap
  this phase closes.
- Never-submit-twice, the human-approval gate, and every existing
  refusal/pause/challenge behavior are unchanged -- verified by running
  the full pre-existing `test_browser_applicator.py`/
  `test_submission_engine.py` suites unmodified except for one mechanical
  signature update (`_open_page` now returns a 4-tuple, not 3) and one
  import-purity allowlist addition (four legitimate stdlib modules
  `diagnostics.py` needs -- `collections`/`dataclasses`/`datetime`/
  `logging` -- none of which weaken the zero-domain-knowledge guarantee
  `test_browser_purity.py` enforces).
- 16 new backend tests (1368 → 1384): pure-asyncio retry-contract tests,
  real-Chromium diagnostics-capture tests, real-Chromium
  retry-actually-recovers/exhausts tests, and an end-to-end
  `SubmissionEngine` diagnostics test. 0 new frontend tests (no frontend
  code touched this phase).

## Deferred, not silently skipped

- **Headless Docker submission.** Still out of scope, per ADR-0076's own
  prior decision -- not reopened here.
- **Retrying the submit click under any circumstance.** Deliberately
  never done, for the never-submit-twice reason stated above. If a
  future phase ever wants this, it needs its own real idempotency-key
  design at the ATS-response level, not a blind retry.
- **Automatic session/browser-crash *recovery*** (relaunching a dead
  browser mid-flow and resuming from where it left off). This phase adds
  *detection and diagnosis* (the failure is now visible, closed cleanly,
  and diagnosable) but not automatic resumption -- a crashed session
  still surfaces as `UNKNOWN`/`FAILED` for a human to look at, per this
  project's existing "never guess, never silently retry a submission
  outcome" discipline (`domain/execution.py`).
- **A configurable retry attempt count / backoff.** Fixed at 3
  attempts / exponential backoff in code, not exposed as a setting --
  no evidence yet that a different value is needed; add one if real usage
  shows otherwise.
