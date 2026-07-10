# ADR-0056: v1.0 prepare-only release scope, release-candidate policy, and supported-platform policy (Phase 34)

- **Status:** Accepted
- **Date:** 2026-07-10
- **References:** ADR-0050 (execution-safety boundary), ADR-0054 (production-
  readiness release gate), ADR-0055 (bounded real-provider release policy),
  ADR-0052 (evidence-grounded CV ingestion), ADR-0044 (Layer-1 precheck),
  ADR-0043 (provider/version-keyed Promptfoo gate)

## Context

Phase 34 is the final v1.0 phase: a release audit and an explicit go/no-go
decision, not a feature phase. A fresh repository-reality audit was run rather
than trusting the phase brief, which referenced a "Phase 33 merge state," a
"Phase 31 live smoke," and "ADR-0059" that **do not exist** in this repository.

**Actual reality (audited):** `origin/main` is at the Phase 30 merge
(`46d267a`, PR #55); the highest existing ADR is **0055**; the ADR index is
continuous; there is **no Phase 31/32/33** and **no ADR-0056–0058**. This ADR is
therefore numbered **0056** (the true next number), not 0059. Baseline on the
audited tree: **667 passed / 0 skipped / 0 failed**, `ruff` clean, `lint-imports`
**4 kept / 0 broken**, wheel + sdist build clean, clean-venv install +
`career-agent --help` + `setup` smoke all pass.

The audit re-proved the safety architecture already established across
ADR-0044/0050/0052/0054/0055 and found it intact. The one release-blocking gap
was **documentation**: the pre-existing `README.md` overclaimed — it described
"submit through a tiered, human-in-the-loop applicator," an Anthropic-only cost
cascade, and a "🚧 scaffolding only / not yet runnable" status — none of which
matches the runnable, Groq-first, prepare-only reality.

## Decision

**Option B (docs + release artifacts + drift-guard tests; no production code).**
The architecture is release-ready and unchanged; only the release *framing* and
*evidence artifacts* were missing. This ADR records three durable decisions.

### 1. Formal v1.0 scope: `PREPARE_ONLY`

v1.0 ships the discover → decide → ingest → confirm → promote → tailor → gate →
ATS → render → journal → report/export workflow. It **does not** submit to any
external system. External submission (browser / email / autonomous) is
**NOT_SUPPORTED**: the code exists but no `Applicator` is constructed by any CLI
path, and the execution boundary is hardcoded fail-closed
(`executor_available=False`, ADR-0050) so every `apply`/`auto` run ends by
reporting "nothing was actually sent." Release docs must not claim autonomous
external submission while this holds. Reachability classification: **UNREACHABLE
(A)**.

### 2. Release-candidate policy

The package version advances to **`1.0.0rc1`**. Rationale: the deterministic
safety architecture is strongly validated offline, but **live-output quality**
and **live Promptfoo/verifier validation** remain user-local and
BLOCKED_BY_CONFIGURATION in any keyless environment (ADR-0055). An `-rc`
designation states "final safety validation is strong; real-provider output
quality is not yet independently validated" without overclaiming a final `1.0.0`.
Promotion `rc1 → 1.0.0` requires: a user-run controlled live smoke with a clean
claim ledger, `verify-promptfoo` PASS against a real provider artifact, and the
`RELEASE_CHECKLIST.md` completed. No tag and no registry publish is performed
here.

### 3. Supported-platform policy

- **Linux:** the supported, exercised platform (full suite green here).
- **Windows:** supported for file I/O correctness — every read/write of user
  content passes an explicit `encoding="utf-8"` (proven by
  `test_encoding_portability.py`), which holds identically on a default Windows
  install (cp1252) by Python's documented `encoding=` contract. Actual Windows
  *execution* is **untested** in this repository (no CI).
- **macOS:** **untested**.

## Consequences

- New/changed (no production code): rewritten `README.md` (accurate prepare-only
  scope, Groq-first providers, runnable quick-start, real command list, privacy
  note); new `SECURITY.md`, `RELEASE_CHECKLIST.md`,
  `docs/release/v1.0.0-rc1-notes.md` (capability matrix + known limitations);
  `pyproject.toml` version `0.1.0 → 1.0.0rc1`; new
  `tests/test_phase34_release_audit.py` drift guards.
- **Unchanged:** truthfulness gate, Promptfoo gate, ATS gate, idempotency,
  journal, execution-safety boundary, CV-ingestion trust model, provider
  selection, prompt version (`truthfulness-gate-v2`), dependencies. No safety
  semantics changed; no external submission newly reachable; no live/paid API
  call made.

## Release decision

**CONDITIONAL_GO** for v1.0.0-rc1, supervised prepare-only. No critical release
invariant is violated (I1–I20 evaluated in the Phase 34 report); required tests,
architecture contracts, and clean-install all pass; external submission is
accurately scoped as unreachable; no secret/private-artifact leakage. The
conditions are the non-critical, enumerated ones: live-output quality unvalidated
in-env, live Promptfoo BLOCKED_BY_CONFIGURATION, no CI in-repo, and Windows/macOS
execution untested.

## Future revisit criteria

Revisit to promote `rc1 → 1.0.0` after a successful user-run live smoke +
`verify-promptfoo` PASS; if CI is added (record its first real check runs); if an
executor is ever wired (which would change the reachability classification and
require re-auditing the entire safety boundary); or on any ADR-0055
evidence-invalidation trigger.
