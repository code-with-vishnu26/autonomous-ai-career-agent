# ADR-0065: Browser Automation Foundation (browser/session/tab lifecycle only)

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0020](0020-browser-tier-session-and-pause.md) (Tier
  2 browser applicator + encrypted session storage),
  [ADR-0026](0026-real-apply-command-and-promptfoo-enforcement.md) /
  [ADR-0050](0050-execution-safety-boundary.md) (execution-safety
  boundary), [ADR-0064](0064-job-search-preferences-separate-from-profile.md)
  (Phase 46, v2 automation-layer arc begins)

## Context

Phase 47 is the second phase of the v2 automation-layer arc (Phase 46 was
the first: Job Search Preferences). It asks for a "Browser Automation
Foundation" -- launch Chrome, reuse sessions, detect login, never
automate login, persist state, multi-tab support -- as a
`browser/browser_manager.py` / `session_manager.py` / `tab_manager.py`
package, explicitly scoped to **not yet apply for jobs**.

Before writing anything, the mandatory repository-reality audit found
this is **not** greenfield: `agents/apply/browser_applicator.py` (651
lines, ADR-0020/ADR-0028/ADR-0032) already drives a real, local Chromium
instance with genuine form-filling, CAPTCHA-pause/resume, and a real
submit-click path -- unwired from the CLI (`ADR-0026`/`ADR-0050`: no
`Applicator(` construction anywhere reachable). It also already has
`integrations/browser_session.py`'s `EncryptedSessionStore`
(ADR-0020) -- encrypted-at-rest, fail-closed session persistence, exactly
the "save browser state" requirement.

## Decision

**Extract and share, don't duplicate.** Three new modules under
`src/career_agent/integrations/browser/` (not a new top-level `browser/`
package -- see "Placement" below):

- **`browser_manager.py`** -- `BrowserManager`: launches/closes Chromium.
  Two modes: `launch_persistent_context()` (a Chrome-native persistent
  profile directory -- cookies/login state survive process restarts
  automatically, no explicit save/load step) and
  `launch()`+`new_context(storage_state=...)` (an ephemeral context seeded
  from a previously saved, encrypted `storage_state` -- the same pattern
  `BrowserApplicator._open_page` already uses internally, now factored out
  and reusable).
- **`session_manager.py`** -- `SessionManager`: wraps the *existing*
  `EncryptedSessionStore` for save/load (reused unchanged, not
  reimplemented), plus the one genuinely new primitive:
  `wait_for_login()`, which polls a caller-supplied CSS selector until it
  appears, or raises `LoginTimeoutError`. **Structurally cannot type a
  credential** -- it has no code path that calls `.fill()`/`.type()`/
  `.press()`/`.press_sequentially()` on anything, verified by an AST-based
  test (`tests/integrations/test_session_manager.py::
  test_source_never_calls_a_fill_or_type_method`), not merely a docstring
  claim. A human logs in directly on the visible page (`headless=False`
  is `BrowserManager`'s default); this module only ever *observes*.
- **`tab_manager.py`** -- `TabManager`: a named registry of Playwright
  `Page`s within one context (`open_tab`/`get_tab`/`close_tab`/
  `list_tabs`/`bring_to_front`).

### Why this is genuinely new work, not a rebuild

`BrowserApplicator`'s browser lifecycle (`_open_page`/`_finish`) is a
single-shot, single-page, single-context flow embedded directly inside
that class, with no persistent-profile mode and no multi-tab support.
Nothing in the existing codebase waits for a human login -- the existing
session store assumes a `storage_state` already represents a logged-in
session. Phase 47 supplies exactly the two capabilities that were missing:
a real login-wait loop, and multi-tab tracking -- while reusing everything
that already existed (`EncryptedSessionStore`, the
`chromium_executable_path` override pattern, the real-local-Chromium test
discipline of `tests/agents/test_browser_applicator.py`).

### Placement: `integrations/browser/`, not a top-level `browser/`

The brief names the package `browser/`. This project's import-linter
"layers" contract only recognizes `agents`/`plugins` → `core` → `domain`
as the layered stack; `storage` and `integrations` are separate,
unlayered branches for I/O boundaries -- `integrations/browser_session.py`
(a real browser's session state) and `integrations/http.py` (a real HTTP
client) already live there. A live Chromium instance is unambiguously
"an integration with an external system," the same category, so the new
modules join it as `integrations/browser/` rather than inventing a new
top-level namespace requiring new layering rules for no architectural
reason. A new, fifth import-linter contract enforces the one property
that actually matters for a foundation layer: **`integrations.browser`
may never import `career_agent.domain`/`.agents`/`.storage`/`.plugins`/
`.llm`** -- it has zero knowledge of what a job opportunity, a résumé, or
an application is, checkable by `lint-imports` and by an AST-based
allowlist test (`tests/integrations/test_browser_purity.py`), the same
enforceable-not-asserted pattern `tests/domain/test_purity.py` already
uses for `domain/`'s zero-I/O contract.

### What this phase explicitly does not do

- **No CLI command.** "This layer does NOT yet apply for jobs. It only
  manages browsers and sessions" -- there is nothing here for a user to
  invoke yet; future phases (adapters, planner, a browser-driven apply
  flow) will be the CLI-facing consumers.
- **No change to `BrowserApplicator`, `FormFiller`, or the execution-safety
  boundary.** `executor_available=False` is still hardcoded; no
  `Applicator(` construction is reachable from the CLI; zero real
  submissions occur, exactly as before this phase.
- **No website-specific logic of any kind** (that is Phase 48's adapter
  framework) and **no automated login** of any kind, on any site, ever.

## Consequences

- New `src/career_agent/integrations/browser/` package: `browser_manager.py`,
  `session_manager.py`, `tab_manager.py`.
- Fifth import-linter contract added (`pyproject.toml`).
- 28 new tests, all driven against a real local Chromium instance (the
  same `/opt/pw-browsers/chromium-*/chrome-linux/chrome` sandbox-path
  discovery `tests/agents/test_browser_applicator.py` already uses, not a
  Python-level fake standing in for a browser), plus two purity tests and
  one AST-based safety guard.
- No new dependency: `playwright>=1.44` was already required
  (`BrowserApplicator`). No version bump -- this is new, additive
  functionality with no CLI surface yet to make it user-visible as a
  release feature.

## Future revisit criteria

Phase 48 (website adapters) is the first real consumer of this
foundation. When it lands, revisit whether `BrowserApplicator`'s own
`_open_page`/`_finish` should be refactored to use `BrowserManager`/
`SessionManager` instead of its private duplicate -- deliberately not
done in this phase, to keep Phase 47's diff to new, additive code only and
avoid touching the existing, already-tested submission-adjacent class
while its own review is out of scope here.
