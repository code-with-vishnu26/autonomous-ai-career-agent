# ADR-0054: Production-readiness release gate — state machine, invariant contract, failure matrix (Phase 28)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** ADR-0048 (idempotency), ADR-0049 (execution journal),
  ADR-0050 (execution-safety boundary), ADR-0051 (setup readiness),
  ADR-0052 (CV ingestion trust boundary), ADR-0053 (truthfulness-re-gated
  revision loop), ADR-0016/0044 (truthfulness gate), ADR-0034 (ATS gate),
  ADR-0043 (Promptfoo provider/version gate)

## Context

Phase 28 asked, with evidence: *can a real user safely operate the app
from setup through discovery and application preparation, recover from
restarts, avoid duplicate attempts, preserve truthfulness, and reach a
controlled prepared state without accidental external submission?* This is
a production-readiness/release-gate phase, not a feature phase.

A fresh audit (HEAD `badaa3e`, baseline **647 passed / 0 skipped**, ruff
clean, import-linter 4/4) found the architecture already satisfies the
requirement; the genuine gap was the absence of (a) a *composed* end-to-end
dry-run proving the pieces work together, and (b) a single consolidated
*release-invariant contract*. **Decision: Option A** — tests + this ADR, no
production code change, no new dependency, no prompt/Promptfoo change. A
`doctor`/`readiness` command was considered and **rejected**: `career-agent
setup` already prints an offline readiness report (ADR-0051); a second
command would duplicate it.

## Core-question answer

**Yes, for the *prepare-only* product it is today.** A user can go setup →
`import-cv` → `promote-cv` → `discover`/`auto` → tailor+gate+ATS → a
prepared application, restart safely, and never trigger an external
submission — because **no external submission is reachable at all** (see
below). The system is release-ready as a *supervised application-materials
preparer*, not as an auto-submitter (which is deliberately unbuilt).

## External-submission reachability (Section 19 — mandatory)

**No real external submission is reachable from any CLI command.** `cli.py`
constructs no concrete `Applicator`, `SubmissionPipeline`, and calls no
`.submit()`/`.prepare()` (every `Applicator` mention is a docstring;
asserted structurally in `test_phase28_release_invariants.py`). `apply`
stops at `confirm_submission()` + the ADR-0050 execution boundary
(`executor_available=False`, always refuses); `auto` is structurally
incapable of confirming/submitting (ADR-0041). Browser/email applicators
exist and are unit-tested against fakes but are unreachable from the CLI.
There are therefore **no irreversible external actions in the product
today** — precise statement, not "submission is safe."

## Reconstructed end-to-end state machine (audit instrument)

| State | Reachable? | Notes |
|---|---|---|
| S0 installed → S1 profile absent | ✅ | |
| S2 scaffolded | ✅ | `setup` (never overwrites) |
| S3 incomplete / S9 ready | ✅ | `load_master_profile`; `MissingSummaryError` fails closed |
| S4 CV ingested → S5 unverified | ✅ | `import-cv`; profile untouched |
| S6 confirmed → S8 promoted | ✅ | `promote-cv`, fail-closed boundary |
| S7 conflicts unresolved | ✅ | REQUIRES_RESOLUTION, no silent overwrite |
| S10 discovered → S11 deduped → S13 ranked | ✅ | `discover`/`auto` |
| S12 hard feasibility | ✅ | Decide hard exclusions before ranking |
| S15 drafted → S16 truthfulness → S17 ATS → S18/S19 revised+re-gated → S20 rendered → S21 prepared | ✅ | `ResumeTailoringPipeline` |
| S22 human confirmation required | ✅ | `apply` only (`confirm_submission`) |
| **S23 external submission attempted** | ❌ **unreachable** | no executor wired (ADR-0050) |
| S24 outcome known | ✅ (manual) | `outcome` command records real-world results |
| **S25 outcome unknown / S26 recovery** | ❌ **unreachable** | no external action can leave an ambiguous outcome yet; the journal (ADR-0049) reconstructs internal stages only |

Fail-closed transitions confirmed: missing summary, truthfulness rejection,
ATS-below-threshold exhaustion, promotion without confirmation/with drift,
missing Promptfoo artifact, prior-attempt duplicate. No fail-open
transition was found on the prepare path.

## Capability matrix (traced, not inferred)

PRESENT_AND_USED: guided setup, profile loading, legal-status capture, CV
ingestion, evidence spans, unverified-fact storage, confirmation binding,
promotion, conflict handling, discovery, dedup, opportunity identity,
scoring, hard feasibility, Pareto/sensitivity/decision advisory, tailoring,
truthfulness gate, Promptfoo gate, ATS gate + revision loop, rendering,
human confirmation (in `apply`), application preparation, idempotency,
execution journal, restart reconstruction, outcome tracking, report,
export, notifications, execution-permission boundary.

DEFERRED_BY_DESIGN (unreachable but built/tested against fakes): real
external submission, browser submission, email submission — gated behind
ADR-0050's named executor-wiring prerequisite. ABSENT: none material to the
prepare-only product. PARTIAL: notifications require config (Telegram/ntfy)
but degrade to no-op.

## Failure matrix (summary; fail-closed unless noted)

| Stage | Injected failure | External side-effect risk | Behaviour |
|---|---|---|---|
| profile load | malformed JSON | none | typed error, clean message, no mutation |
| CV parse | malformed/oversized/unsupported | none | typed `DocumentParseError`/`UnsupportedDocumentError`, no mutation |
| promotion | no-confirm / drift / conflict | none | REJECT / REQUIRES_RESOLUTION, never overwrites |
| discovery | source raises | none | per-source log-and-skip, other sources continue |
| scoring/Pareto/sensitivity | n/a (deterministic) | none | reproducible; exclusions never reversed |
| drafter | raises | none | propagates (`auto` prints "not prepared", continues) |
| truthfulness verifier | raises | none | explicit block (never a silent pass) |
| ATS gate | retries exhausted | none | `AtsScoreBelowThresholdError` (fail closed) |
| renderer | PDF converter missing | none | DOCX still written; PDF absence is structurally visible, not swallowed |
| application-store write | duplicate id | none | append-only `INSERT OR IGNORE`; ADR-0048 guard pre-checks |
| journal write | — | none | append-only; a missing event is a forensic gap, never a duplication risk (ADR-0048 still blocks) |
| notification | delivery fails | none | logged and swallowed (ADR-0005: notify, never gate); never rolls back business state or resubmits |
| external submission | — | **n/a — unreachable** | — |

## Release-invariant contract (I1–I22) and where proven

| # | Invariant | Proven by |
|---|---|---|
| I1 | setup never overwrites a profile | `test_setup_command` |
| I2 | ingestion alone never mutates MasterProfile | `test_cv_ingest_cli`, `test_phase28_end_to_end` |
| I3 | imported facts UNVERIFIED until confirmed | `test_ingestion`, e2e |
| I4 | confirmation is content-bound | `test_ingestion` |
| I5 | source drift invalidates promotion | `test_cv_ingest`, e2e |
| I6 | conflicting trusted value never silently overwritten | `test_cv_ingest`, e2e |
| I7 | hard exclusions not reversed by ranking/Pareto | `test_cli_decision_intelligence`, ADR-0046/0047 |
| I8 | every revised resume fully re-gated | `test_ats_gate_loop` B3, `test_phase27_revision_authority` |
| I9 | truthfulness-rejected revision never ATS-scored | `test_ats_gate_loop` B3 |
| I10 | retry exhaustion fails closed | `test_ats_gate_loop` B4 |
| I11 | missing Promptfoo blocks live-verifier path | `test_phase28_release_invariants` |
| I12 | tests cannot reach real Groq/Anthropic | `conftest`, `test_phase28_release_invariants` |
| I13 | duplicate prior attempts handled (ADR-0048) | `test_cli_auto`, e2e restart |
| I14 | restart preserves journal history | `test_run_journal`, e2e restart |
| I15 | journal record ≠ proof of external success | `test_phase28_release_invariants` (no such event exists) |
| I16 | no real external submission in tests | structural (`test_phase28_release_invariants`) |
| I17 | no machine-local Promptfoo artifact needed for unit tests | `test_phase28_release_invariants` |
| I18 | UTF-8 survives setup→ingestion→persistence | `test_encoding_portability`, e2e (José/工程师/🚀) |
| I19 | untrusted JD text never becomes evidence | `test_phase27_revision_authority` |
| I20 | Phase 26 unverified facts can't enter resume pipeline | `test_phase27_revision_authority` (import isolation) |
| I21 | no release test weakens a safety assertion | this phase added none; review-enforced |
| I22 | no live paid API call required | whole suite runs offline |

All evaluated invariants hold; none violated; none unprovable within the
current (prepare-only) architecture. No counterexamples found.

## Consequences

- New tests only: `tests/test_phase28_end_to_end.py` (composed journey +
  restart-idempotency + UTF-8 survival, Aarav-Rao synthetic fixture
  generated in-test, no committed binary) and
  `tests/test_phase28_release_invariants.py` (the cross-cutting contract).
- No production code, no dependency, no prompt-version bump, no Promptfoo
  artifact change; truthfulness/ATS/idempotency/journal/Phase-26 semantics
  all unchanged; no external submission newly reachable.

## Remaining risks / not-guaranteeable

- Real LLM output quality is unvalidated here (no live calls, by design);
  the truthfulness gate bounds *safety*, not resume quality.
- The moment an executor is ever wired, the S23–S26 states and ADR-0050's
  deferred write-ahead-intent + ack-classifier become mandatory before
  release — this ADR's "no irreversible action" guarantee is scoped to the
  current, executor-less product.

## Recommended Phase 29

A supervised, single-opportunity **live smoke test harness** the *user*
runs manually (real Groq truthfulness validation via Promptfoo, one real
tailored resume) — explicitly outside the automated suite, still stopping
at prepared/confirmed, still no external submission.
