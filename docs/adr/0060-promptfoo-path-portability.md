# ADR-0060: runtime path resolution must be CWD-relative and Settings-overridable, never install-tree-relative (Phase 40)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0043 (provider/version-keyed Promptfoo gate), ROADMAP.md
  Phase 39's v1.1 backlog (the finding this phase closes)

## Context

Phase 39's post-release onboarding audit found a real, evidence-backed P1
defect: `career-agent`'s default Promptfoo results directory was computed
as

```python
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PROMPTFOO_RESULTS_DIR = _REPO_ROOT / "promptfoo" / "results"
```

`__file__` only points at the source checkout for an **editable** install
(`pip install -e .`). A wheel or a plain `pip install .` copies
`cli.py` into `site-packages`, so this resolved to a nonsensical,
non-writable-by-convention `site-packages/promptfoo/results` — and the
`promptfoo/` configs `npx promptfoo` needs aren't packaged in the wheel at
all. Reproduced directly in this phase: a fresh wheel install, run from a
directory outside the repository, reported exactly this broken path before
the fix.

Critically, this was the **only** user-writable/user-configurable runtime
path in the codebase resolved this way. `database_path` and
`artifacts_dir` (`Settings`, `core/config.py`) were already correctly
CWD-relative, `.env`-overridable defaults (`"data/career_agent.db"`,
`"data/artifacts"`) — the Promptfoo path was the sole architectural
outlier, not a case needing a new design.

## Decision

**Fix by consistency, not by inventing a new mechanism.** Add
`promptfoo_results_dir: str = "promptfoo/results"` to `Settings`, exactly
mirroring `database_path`/`artifacts_dir`: CWD-relative, overridable via
`.env`/`PROMPTFOO_RESULTS_DIR`. Delete `_REPO_ROOT`/
`_DEFAULT_PROMPTFOO_RESULTS_DIR` entirely; every call site (`setup`,
`apply`, `auto`, `verify-promptfoo`, `diagnose-promptfoo-drift`) now
resolves its default from `Settings.promptfoo_results_dir`, constructed
fresh per call — never a shared module-level constant computed once at
import time from install location.

**This is a durable policy, not merely a bugfix**, worth an ADR precisely
because it generalizes: *no future runtime path in this codebase may be
derived from `__file__`/install-tree layout.* Every user-writable or
user-configurable path is a `Settings` field, CWD-relative by default,
`.env`-overridable, and constructed at call time. A future contributor
adding a new local-state path (a cache dir, an export default, anything
else the CLI writes to or reads from at runtime) should follow this
pattern by default, not re-derive `__file__`-based resolution and
reintroduce the same install-mode-dependent bug class.

Explicit CLI overrides (`--results-dir`, already present on
`verify-promptfoo`/`diagnose-promptfoo-drift`) are unchanged and still take
precedence over the `Settings` default.

## What did not change

Promptfoo gate semantics (ADR-0043/0044) are untouched — this only changes
*where the default path is computed from*, never *what counts as a valid
artifact* or *whether the gate can be bypassed*. Fail-closed behavior is
identical: no artifact at the resolved path still blocks exactly as before.
No new dependency. No prompt-version change.

## Consequences

- `src/career_agent/core/config.py`: `Settings` gains
  `promptfoo_results_dir: str = "promptfoo/results"`.
- `src/career_agent/cli.py`: `_REPO_ROOT`/`_DEFAULT_PROMPTFOO_RESULTS_DIR`
  removed; five call sites now resolve from `settings.
  promptfoo_results_dir` (three already had a `Settings` instance in
  scope; the two standalone `verify-promptfoo`/`diagnose-promptfoo-drift`
  helpers now construct one).
- `tests/test_cli_auto.py`: one test that monkeypatched the now-removed
  module constant updated to set `PROMPTFOO_RESULTS_DIR` via the
  environment instead (the same override path a real user would use).
- New `tests/test_phase40_promptfoo_path_portability.py` (6 tests): default
  is relative/CWD-relative, env-overridable, `setup`'s reported path
  reflects the actual cwd (not an install-time location), `verify`/
  `diagnose` share identical resolution, an explicit path still wins, and
  the removed constants do not reappear.
- Reproduced live (not merely asserted): both an editable-install run and a
  fresh wheel-install run, each launched from a directory outside the
  repository, now report a CWD-relative `promptfoo/results` path instead
  of an install-tree path.

## Future revisit criteria

Revisit if a genuine need emerges for a machine-wide (not per-project)
default location (e.g. an XDG-style user config directory) — that would be
a considered addition to this same policy, not a reversal of it.
