# ADR-0059: v1.0.0 release promotion decision (Phase 37)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0055 (bounded real-provider release policy), ADR-0056
  (v1.0 prepare-only scope, release-candidate policy), ADR-0057 (CI and
  cross-platform hardening), ADR-0058 (confirmation lifecycle fix)

## Context

Phase 37's question: can `1.0.0rc1` honestly become `1.0.0`? ADR-0056 set
`CONDITIONAL_GO` with four named conditions. This phase re-audited
repository reality fresh (not trusting prior reports) and checked whether
those conditions are now closed by real, independently-verified evidence.

### Repository reality (verified fresh, this phase)

`origin/main` at `833c5db` — confirmed as the real merge commit of PR #58
(Phase 36's fix) via `git log`, not assumed. Highest ADR before this one:
0058. Package version before this ADR: `1.0.0rc1`. No git tag exists yet.

### CI (verified via the GitHub Actions API directly, not inferred from YAML)

The `push` event run triggered by the `833c5db` merge
(`workflow run 29086438605`) is **`status: completed`, `conclusion:
success`**, on **both** matrix legs:

- `verify (ubuntu-latest)`: every step (`Ruff`, `Import-linter`, `Test
  suite`, `Build wheel + sdist`, `Verify release artifacts`, `Clean-venv
  install + CLI smoke`) `completed`/`success`.
- `verify (windows-latest)`: same, all `completed`/`success`.

This directly resolves Phase 36's open question ("CI's actual final
pass/fail on this merge is unverified") with a genuine result, not an
assumption: **CI is green on both platforms for the exact commit this
release is built from.**

### Local baseline (this session, fresh)

`pytest`: **682 passed / 0 skipped / 0 failed**. `ruff check .`: clean.
`lint-imports`: **4 kept / 0 broken**. Identical to CI's own count.

### Live evidence (Phase 36, independently re-examined here)

The maintainer's real transcript (real `GROQ_API_KEY` presence-confirmed,
real `verify-promptfoo --provider groq` → PASS) was re-inspected line by
line in this phase, not merely re-cited:

- The rendered resume text contains only facts present in the synthetic
  trusted profile (Python, REST APIs, PostgreSQL, Docker, pytest, Git).
- The adversarial JD injection line's targets ("8 years of Kubernetes
  experience", "led 20 engineers", any "Senior" framing) do **not** appear
  anywhere in the rendered output — checked directly against the pasted
  text, not asserted from policy alone.
- ATS score `78.125` and `truthfulness_approved=1` are real values read
  from the SQLite row in the transcript, not fabricated.

### Post-merge fix confirmation (user-supplied, real Windows evidence, not personally executed by this agent)

After PR #58 merged, the maintainer independently re-ran the real Windows
CLI against a **fresh** synthetic opportunity (`phase36-jd-junior-backend-
retest`) specifically to confirm the shipped fix, not just the offline
regression test:

1. First `apply` run: tailored, truthfulness-approved, ATS-scored, DOCX
   rendered, confirmation reached, declined (`N`). The resulting row:
   `status=declined`, `truthfulness_approved=1`, `ats_total=78.125`,
   `prompt_version=truthfulness-gate-v2`.
2. Second `apply` run, **same opportunity id**: **not** blocked by the
   idempotency guard — tailoring ran again, truthfulness approved again, a
   DOCX was rendered again, confirmation was reached again, declined again.

This is real, independent, post-merge confirmation that `decline → status
recorded as declined → retry remains allowed` holds on the actual Windows
CLI + SQLite path, not only in the offline fake-backed regression test this
ADR already cites. Zero external submissions occurred in either run. The
original pre-fix opportunity (`phase36-jd-junior-backend`, stuck at
`status=pending`) is left untouched as historical evidence of the original
defect — no historical user-local data was mutated to produce this
confirmation.
- Token usage and monetary cost were **not** exposed by that run's output;
  this ADR states them as **UNKNOWN**, consistent with ADR-0055's existing
  disclaimer, rather than inventing a number.

## Decision

**GO. Promote `1.0.0rc1` → `1.0.0`.**

All four of ADR-0056's `CONDITIONAL_GO` conditions are now closed:

1. **Live-output quality unvalidated** → resolved by the real Phase 36
   smoke (above).
2. **Live Promptfoo BLOCKED_BY_CONFIGURATION** → resolved for the
   maintainer's own environment (a real PASS was observed); still, by
   design, a user-local fact — CI itself can never reproduce this, since it
   is never given a key (ADR-0055's own architecture, unchanged).
3. **No in-repo CI** → resolved (ADR-0057), and now independently confirmed
   green on the exact release commit (above), not merely present.
4. **Windows/macOS execution untested** → Windows is resolved (both by CI
   and by the maintainer's real local Windows run); **macOS remains
   untested** — this was always a named, deliberate, cost-driven gap
   (10x CI runner-minute multiplier under GitHub's private-repo billing),
   not an oversight, and does not block promotion on its own merit (a
   platform gap that is disclosed is a documented limitation, not a
   release-blocking defect).

No release invariant is violated: no unsupported claim survived the real
live run; no injection-derived claim survived; external submission remains
**UNREACHABLE** (unchanged, re-confirmed: no `Applicator` construction
anywhere in `src/`); no secret or private candidate data is present in any
tracked file or built artifact; idempotency (ADR-0048, patched by
ADR-0058) and the append-only journal (ADR-0049) are both re-proven by the
full test suite; the Promptfoo gate (ADR-0043) is unmodified and unbypassed.

## What this release does and does not claim

- **Claims:** the deterministic safety architecture (truthfulness,
  idempotency, execution boundary, CV trust) is proven both offline
  (hundreds of tests) and now under one real, live, adversarial-JD sample;
  the package installs cleanly and runs correctly on Linux and Windows via
  automated CI.
- **Does not claim:** statistical output-quality reliability across
  candidates/JDs/provider versions (one real sample, explicitly
  disclaimed); macOS compatibility (untested, not asserted); any bound on
  real-world monetary cost (UNKNOWN, not estimated).

## Consequences

- `pyproject.toml` version: `1.0.0rc1` → `1.0.0`.
- `tests/test_phase34_release_audit.py::test_release_candidate_version_is_pinned`
  updated to assert `1.0.0` (a deliberate, evidenced promotion, not a
  weakened test).
- New `docs/release/v1.0.0-notes.md` (final release notes, the
  condition-by-condition closure table, and the real live-evidence
  summary). The historical `docs/release/v1.0.0-rc1-notes.md` is kept
  unedited, with a one-line "superseded by" pointer added at its top —
  the historical decision record is never rewritten.
- `README.md` status line and release-notes link updated to `v1.0.0`.
- `ROADMAP.md` gets a new Phase 37 entry (this phase); no prior phase entry
  is edited.
- New `tests/test_phase37_v1_release_promotion.py` pins: the version is
  exactly `1.0.0` (no `-rc` suffix), the new release-notes file exists, this
  ADR exists, and the historical rc1 notes file is preserved with its
  superseded-by pointer.
- **No production code changed.** No safety semantics changed. No new
  dependency. No prompt-version change. No Promptfoo artifact touched or
  regenerated by this phase. **No git tag created; nothing published to any
  registry** — both explicitly out of scope for this phase, left for the
  maintainer.

## Future revisit criteria

Revisit if a subsequent live sample reveals a safety defect (triggers a
NO_GO reassessment, same bar as every prior phase); if macOS support is
ever added (promote that platform row from "untested" to "exercised"); or
if cost/token visibility is ever added to the CLI's output (replace
"UNKNOWN" with real, observed numbers, never an estimate).
