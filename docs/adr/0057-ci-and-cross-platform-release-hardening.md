# ADR-0057: CI, cross-platform release hardening, and reproducible packaging validation (Phase 35)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0056 (v1.0 prepare-only scope, release-candidate policy,
  supported-platform policy), ADR-0054 (production-readiness release gate),
  ADR-0055 (bounded real-provider release policy)

## Context

Phase 34's audit identified the project's one substantive remaining
engineering gap: **there is no `.github/` directory at all** — no CI exists.
Every prior release audit (lint, tests, import-linter, packaging,
clean-install, cross-platform reasoning) had to be run manually, and the
"Windows" and "macOS" columns of the supported-platform policy (ADR-0056)
rested on *static* reasoning (explicit `encoding="utf-8"`) rather than actual
execution — a real gap the ADR named honestly rather than papering over.

A fresh Phase 35 audit reconfirmed the baseline unchanged since Phase 34:
`origin/main` at `560c6a7` (the Phase 34 merge), **672 passed / 0 skipped / 0
failed**, `ruff` clean, `lint-imports` **4 kept / 0 broken**, version
`1.0.0rc1`. No new feature gap was found; the task is purely reproducibility
and release-confidence infrastructure.

## Decision

Add a single GitHub Actions workflow (`.github/workflows/ci.yml`) and two
small, reusable release-tooling scripts. No production code changes; no
safety semantics changed.

### CI workflow shape

- **Trigger:** `push` to `main` and every `pull_request` into `main`.
- **Permissions:** `contents: read` only — the workflow never writes to the
  repository, never tags, never publishes.
- **No secret is ever referenced.** This is a structural guarantee, not a
  policy statement: since no step reads `secrets.*`, a real Groq/Anthropic
  API key is never available to the workflow, so it is **impossible** for CI
  to make a live/paid LLM call (reinforcing, at the CI level, the
  `tests/conftest.py` network-block fixture that already blocks it at the
  test level).
- **Matrix:** `ubuntu-latest` × `windows-latest`, Python 3.11 (the pinned
  `requires-python` floor). **macOS is deliberately excluded** — GitHub
  Actions' macOS runners carry a 10× minute multiplier on private repos, and
  ADR-0056 already named macOS an accepted, explicit gap rather than a
  silent one; adding it is not justified by evidence of a macOS-specific
  defect. This can be revisited without re-opening any safety question.
- **Steps, in order:** checkout → setup Python 3.11 (pip-cached) → editable
  install with dev extras → `ruff check .` → `lint-imports` → `pytest` →
  `python -m build` → `scripts/verify_release_artifacts.py` →
  `scripts/smoke_test_wheel.py`. No `continue-on-error`, no broad exception
  swallowing, no `errors="ignore"`.
- **Concurrency:** a new push cancels the previous in-flight run for the same
  ref, bounding total CI minutes.

### New release-tooling scripts (replace ad hoc Phase-34 shell logic)

- **`scripts/verify_release_artifacts.py`** — builds on the wheel-inspection
  logic Phase 34 ran by hand; now checks **both** the wheel and the sdist,
  fails closed on a missing/malformed archive, and fixes two false positives
  found while writing it: `.env.example` (a safe, secret-free, intentionally
  committed template) must not be flagged as a real `.env`; and `tests/`
  belongs in the **sdist** by normal Python packaging convention (a source
  distribution is meant to be buildable/testable) and is only forbidden in
  the **wheel**.
- **`scripts/smoke_test_wheel.py`** — a single, OS-branch-free Python script
  (using `venv`/`subprocess`/`pathlib` only) that creates a throwaway venv,
  installs the freshly built wheel, and runs `career-agent --help` and
  `career-agent setup` in a scratch directory. Runs identically on Linux and
  Windows via the *same* command, rather than duplicating the logic as
  OS-conditional YAML steps that could quietly drift apart.

Both scripts are dependency-free beyond the standard library, so they add no
new runtime or dev dependency; `build>=1.2` is added as an explicit dev
dependency (it was previously installed ad hoc, undeclared).

### Supported-platform policy amendment

ADR-0056's platform table is updated from *reasoning* to *evidence*:

| Platform | Before (ADR-0056) | After (this ADR) |
|---|---|---|
| Linux | exercised (local) | exercised **in CI**, every push/PR |
| Windows | UTF-8 enforced statically; execution untested | **exercised in CI**, every push/PR — real install, real smoke, real test suite |
| macOS | untested | still untested — a named, deliberate cost trade-off, not silently dropped |

## What this proves and what it does not

- Proves: the full test suite, architecture contracts, and a real
  build→install→smoke cycle succeed on a **real** Windows runner, not by
  inference from Linux.
- Does **not** prove: live LLM output quality, live Promptfoo validation, or
  anything requiring a real provider key — CI structurally cannot do this
  (no secret is available to it), and ADR-0055's user-run local smoke
  procedure remains the only path to that evidence.
- This ADR's claims about CI passing are only as good as an actual observed
  run; per the operating rule "do not claim CI passed unless the actual run
  passed," the PR body for this phase records the real, checked run
  conclusion rather than assuming success from the YAML being syntactically
  valid.

## Consequences

- New: `.github/workflows/ci.yml`, `scripts/verify_release_artifacts.py`,
  `scripts/smoke_test_wheel.py`, `tests/test_phase35_ci_release_tooling.py`
  (6 tests: `.env`/`.env.example` distinction, wheel-vs-sdist test-path rule,
  DB/spreadsheet/Promptfoo-results detection, workflow fail-closed shape,
  both-OS coverage, no-secret-reference).
- Changed: `pyproject.toml` adds `build>=1.2` to `dev` extras;
  `.env.example`'s stale Anthropic-only-cascade comment corrected to name
  Groq (preferred) alongside Anthropic, matching the actual provider-selection
  order documented in ADR-0055/README since Phase 34.
- **Unchanged:** truthfulness gate, Promptfoo gate, ATS gate, idempotency,
  journal, execution-safety boundary, CV-ingestion trust model, provider
  selection, prompt version, model identifiers, dependencies (beyond the one
  declared dev-tooling addition). No safety semantics changed; no external
  submission newly reachable; no live/paid API call is possible from CI by
  construction.

## Future revisit criteria

Revisit if CI minute cost ever becomes material (e.g. add a schedule/caching
change); if a macOS-specific defect is ever found (justifying the 10× runner
cost); if `requires-python` changes (add a Python-version axis to the
matrix); or if a future phase wires a real executor (which would require
re-auditing whether CI's read-only, secret-free design still guarantees no
live external action is possible).
