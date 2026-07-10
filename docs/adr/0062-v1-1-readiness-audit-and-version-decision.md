# ADR-0062: v1.1 production-readiness audit, SemVer decision, and release gate (Phase 43)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0056 (v1 prepare-only release scope), ADR-0059
  (v1.0.0 release promotion), ADR-0060 (promptfoo runtime-path
  portability), ADR-0061 (sdist allowlist + classifier accuracy)

## Context

Phase 43 audited the repository's readiness to cut a **v1.1** release,
covering eight categories against directly-observed evidence, and reached a
version decision by actual SemVer reasoning rather than by assuming the
"v1.1" label in the phase title.

This ADR records the **decision and its evidence**. It does **not** bump any
version, write release notes, or create a tag — that is Phase 44's job,
gated on owner authorization. The `v1.0.0` tag is immutable and untouched
(annotated tag object; peeled commit `b8414e3`).

## What actually changed since the v1.0.0 tag

Every commit on `main` since the `v1.0.0` tag was enumerated (Phases 38–42).
The **only runtime source change** is:

| File | Change | SemVer impact |
|------|--------|---------------|
| `src/career_agent/core/config.py` | +6 lines: new `promptfoo_results_dir` `Settings` field (CWD-relative default `promptfoo/results`, env-overridable, same pattern as `database_path`/`artifacts_dir`) | **New backward-compatible functionality → MINOR** |
| `src/career_agent/cli.py` | Replaced the `__file__`-based `_REPO_ROOT`/`_DEFAULT_PROMPTFOO_RESULTS_DIR` constants with `settings.promptfoo_results_dir` at 5 call sites; removed a dead duplicate `return 0`; help/docstring text | Bugfix (wheel-install path) + refactor |

Everything else (Phases 38, 39, 41, 42) touched only **docs, tests,
packaging metadata, and CI/dev tooling** — no runtime `src/` behavior:
classifier `Pre-Alpha → Production/Stable`, sdist top-level allowlist,
`requirements.txt` comment, README onboarding accuracy, and new regression
tests.

**Crucially, no LLM-facing code changed** — the truthfulness gate, both
`ClaimVerifier` implementations, the prompt text, and the promptfoo prompt
version (`truthfulness-gate-v2`) are byte-identical to v1.0.0.

### Behavior-compatibility analysis

For the **documented, supported** usage (editable install, run from the
repo root), the old `_REPO_ROOT` equalled the current working directory, so
the old install-tree-relative path and the new CWD-relative default resolve
to **the same** `promptfoo/results`. The behavior only *changes* for the
previously-broken wheel/non-editable case, where the old `__file__`-based
path pointed uselessly into `site-packages`. So: **no breaking change for
supported usage; a strict bugfix for the unsupported-but-now-fixed case;
plus one new, optional, backward-compatible configuration knob.** No
dependency versions changed.

## Decision

### 1. Version: **v1.1.0** (MINOR)

Per SemVer 2.0.0, a MINOR bump is correct "when you add functionality in a
backward compatible manner." The new `promptfoo_results_dir` `Settings`
field is exactly that — a documented (ADR-0060), `.env`-overridable
configuration surface that did not exist in v1.0.0 — bundled with a
backward-compatible bugfix.

- **Not v1.0.1 (PATCH):** that would understate the release. A PATCH is
  "backward compatible bug fixes" *only*; this release also adds a new
  public configuration field, which is functionality, not merely a fix.
- **Not "remain unreleased":** the audit found no P0/P1 blocker, and the
  changes (a real wheel-install bugfix, packaging hardening, and onboarding
  accuracy) are worth shipping.

### 2. Release gate: **CONDITIONAL_GO**

GO to v1.1.0, conditioned on the following Phase 44 mechanics being executed
correctly (none is a discovered risk — they are the normal cost of a
version bump):

- Bump `pyproject.toml` `version` `1.0.0 → 1.1.0` **in lockstep** with the
  three v1.0.0 drift-guard tests that hard-pin `version("career-agent") ==
  "1.0.0"` (`test_phase34_release_audit.py`,
  `test_phase37_v1_release_promotion.py`,
  `test_phase38_post_release_audit.py`). These must be **updated, not
  weakened** — they are legitimate release-version guards that should now
  guard `1.1.0`.
- Write `docs/release/v1.1.0-notes.md`; keep the v1.0.0 notes intact.
- Observe a fresh green CI on the bump commit (both `ubuntu-latest` and
  `windows-latest`) before any promotion.
- Owner authorization for the actual tag/GitHub Release (the agent prepares
  exact commands; it does not push the tag itself).

**No fresh live-LLM validation is required for v1.1.0**, because zero
LLM-facing code changed since v1.0.0. The v1.0.0 controlled live-Groq
evidence (Phase 36/ADR-0059) carries forward unchanged; the promptfoo
prompt version is identical.

## Audit results (eight categories)

| Category | Outcome | Evidence |
|----------|---------|----------|
| Architecture | PASS | `lint-imports` 4 contracts kept/0 broken; layered package intact |
| Safety (prepare-only) | PASS | `executor_available=False` hardcoded; no `Applicator` wired; apply/auto fail-closed (Phase 42, directly observed) |
| Truthfulness | PASS | fabrication gate + promptfoo gate fail-closed; gate code byte-identical to v1.0.0 |
| Packaging | PASS | fresh wheel (86 entries) + sdist (285) verified, none forbidden, allowlist passes; wheel smoke OK |
| Onboarding | PASS | journeys A–H validated (Phase 42); README/scaffold accuracy guarded |
| Secrets | PASS | no `.env`/DB/keys/profile tracked; presence-only key reporting |
| Release-consistency | PASS (at 1.0.0) | `pyproject`=1.0.0, tag=1.0.0, drift-guards pin 1.0.0 — all consistent now; version bump is Phase 44's job |
| CI | PASS | matrix Ubuntu+Windows; no `continue-on-error`; green on the last three merged PRs |

### Risk register

| ID | Risk | Severity | Status |
|----|------|----------|--------|
| R1 | Version bump must update three drift-guard tests in lockstep or CI fails | P2 | Deferred to Phase 44 (expected release mechanics, not a defect) |
| R2 | Live-LLM output *quality* is unverifiable in the CI/sandbox (no key, egress blocked) | P3 | Accepted — carried from v1.0.0; no LLM-facing change since |
| R3 | macOS + full Windows/PowerShell onboarding unexercised here | P3 | Accepted/documented gap (README); CI covers Windows headless |

No P0 or P1 items were found.

## Consequences

- One decision ADR; `ROADMAP.md` and `docs/adr/README.md` updated.
- No version bump, release notes, or tag in this phase — those are Phase 44,
  under owner authorization.
- The `v1.0.0` tag and all prior release evidence remain immutable.

## Future revisit criteria

If, before Phase 44 executes, any **LLM-facing** code or the promptfoo
prompt version changes, the "no fresh live validation required" conclusion
is void and a new controlled live run must gate the release.
