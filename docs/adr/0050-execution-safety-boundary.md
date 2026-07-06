# ADR-0050: Formal execution-safety boundary for irreversible submissions (Phase 24)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0048](0048-application-attempt-idempotency-guard.md)
  (application-attempt idempotency, composed with this boundary),
  [ADR-0049](0049-append-only-execution-journal.md) (the execution journal
  this boundary emits into, and which named this boundary as its deferred
  prerequisite), [ADR-0018](0018-submission-safety.md) (token-bound
  confirmation), [ADR-0021](0021-email-tier-draft-only.md) (email is
  draft-only), [ADR-0027](0027-applicant-identity-snapshot.md) (Tier-1
  direct-API submission recorded dead), [ADR-0036](0036-worldwide-job-board-sources.md)
  (manual-only Tier-C sources)

## Context

Phase 24's brief asked to "design and implement the smallest justified
production execution boundary that can safely connect an application
execution mechanism to the existing architecture," preserving human
confirmation, truthfulness, provider policy, idempotency, append-only
history, and fail-closed behavior -- and it explicitly permitted the
conclusion "do not wire a real executor yet" if repository reality
warranted it.

A fresh repository-reality audit (not memory) established the decisive
facts, all with code evidence:

- **No irreversible external action is reachable from any CLI command.**
  `cli.py` imports zero `Applicator`s (every grep hit is docstring text).
  `_apply_pipeline` uses `result.submittable` only for its `is None`
  rejection check -- it never calls `.prepare()`/`.submit()` and never
  constructs a `SubmittableApplication`; it ends at `confirm_submission()`
  and prints "Nothing was actually sent." `run_auto_command` never even
  reaches confirmation (ADR-0041). The three applicators
  (`TieredApplicator`/`BrowserApplicator`/`EmailApplicator`) and
  `SubmissionPipeline` exist and are unit-tested against fakes, but are
  reachable only from tests.
- **No executor is safe to wire, independent of reachability.** ADR-0027
  recorded every Tier-1 fully-automated direct-API path dead across
  Greenhouse/Lever/Ashby. `BrowserApplicator.submit()` infers success from
  "no challenge selector visible after the click" -- the exact
  "no-exception-means-success" anti-pattern the brief forbids (I9, RQ13);
  it has no provider-side receipt or application-id evidence. Email is
  draft-only by ADR-0021 (`EmailDraftSink` has no `send`). So no current
  executor can produce a *definite* acknowledgement, which is a
  precondition for safe irreversible submission.
- **Provider policy exists only as prose** (ADR-0036 Tier-C "manual-only",
  standing invariant 7) plus plugin-local behavior -- no first-class
  policy object, and no policy decision anywhere before a (nonexistent)
  execution.
- **No `OUTCOME_UNCERTAIN` vocabulary exists.** `Application.status` is
  `pending | paused_for_human | submitted | failed | rejected`; nothing
  distinguishes "definitely failed before submitting" from "timed out,
  possibly submitted."

ADR-0049 already named exactly this gate -- a deterministic boundary
enforcing "uncertain external effect ⇒ never auto-replay," gating any
future executor wiring -- as the mandatory prerequisite before any real
`Applicator` is connected. Phase 24 builds that prerequisite.

## Decision (Option C: boundary now, executor never in this phase)

Introduce a **pure, deterministic, exhaustively-verified execution-safety
boundary** (`domain/execution.py`), and wire it into the one reachable
pre-execution point (`_apply_pipeline`, immediately after human
confirmation) with `executor_available=False` hardcoded -- so it always
refuses, with an explicit journaled reason, changing no external behavior.
**No real executor is wired. No external submission becomes reachable.**
This satisfies rule 30 (every irreversible action must have an explicit
boundary) by making the boundary explicit and live *before* the action it
guards can occur, rather than leaving "nothing submits" as an implicit
accident of un-wired code.

### Formal model

**Submission outcome** (the mandatory four-way distinction, Section 3):

```
Y ∈ { NOT_ATTEMPTED, DEFINITELY_NOT_SUBMITTED,
      DEFINITELY_SUBMITTED, OUTCOME_UNCERTAIN }
```

`OUTCOME_UNCERTAIN` is never collapsed into failure. The acknowledgement
mapping `outcome_from_ack` is total and the load-bearing row is
`AMBIGUOUS → OUTCOME_UNCERTAIN`: ambiguous evidence can never become a
definite result. There is no default-to-success and no default-to-failure.

**Retry admissibility:**

```
retry_allowed(Y, unresolved_intent, policy) =
    policy ∈ {ASSISTED, AUTOMATED}
    ∧ ¬unresolved_intent
    ∧ Y ∈ {NOT_ATTEMPTED, DEFINITELY_NOT_SUBMITTED}
```

Hence `Y = OUTCOME_UNCERTAIN ⇒ retry_allowed = false` and
`Y = DEFINITELY_SUBMITTED ⇒ retry_allowed = false`, unconditionally --
the required safety property. A definite *pre-effect* failure is retryable
only *according to policy*, never merely because "the last attempt
failed."

**Execution permission** (fail-closed; `allowed=True` only when every
positive condition holds):

```
execute_allowed(request) = ALLOW  iff
    executor_available
    ∧ policy ∈ {ASSISTED, AUTOMATED}
    ∧ confirmation_present
    ∧ artifact_matches
    ∧ ¬journal_has_unresolved_intent
    ∧ prior_outcome ∈ {NOT_ATTEMPTED, DEFINITELY_NOT_SUBMITTED}
```

Each adverse condition maps to exactly one closed-vocabulary refusal
reason (`REFUSED_NO_EXECUTOR`, `REFUSED_MANUAL_ONLY_SOURCE`,
`REFUSED_UNKNOWN_SOURCE_POLICY`, `REFUSED_NO_CONFIRMATION`,
`REFUSED_ARTIFACT_MISMATCH`, `REFUSED_PRIOR_SUBMITTED`,
`REFUSED_PRIOR_UNCERTAIN`, `REFUSED_UNRESOLVED_INTENT`). The permission
decision consumes **only** these six safety factors -- it has no field for
ranking score, Pareto status, ATS score, or truthfulness result, so none
of those can ever authorize a submission (I16-I19, proven structurally by
a test asserting the `ExecutionRequest` field set).

**Source policy** (`resolve_source_policy`, deterministic, closed-vocab,
fail-closed): Tier-C/unstructured sources → `MANUAL_ONLY`; recognized ATS
kinds (greenhouse/lever/ashby, which have human-in-the-loop browser flows)
→ `ASSISTED`; recognized structured source with no automatable target →
`MANUAL_ONLY`; unrecognized → `UNKNOWN` (treated as manual for
permission). **No source maps to `AUTOMATED`** -- ADR-0027 killed every
fully-automated path.

**Artifact identity** (`confirmed_artifact_digest`): a reference,
order-independent (over answers) integrity digest over
`(opportunity_id, rendered_content, target, tier, sorted answers)` with an
unambiguous field separator. The boundary consumes only the resulting
`artifact_matches` boolean; the digest is the contract a future executor
uses to detect post-confirmation mutation. This is an integrity digest for
equality, not a cryptographic authenticity claim.

### Exhaustive verification

The boundary's entire input space is finite and small:
`4 × 2 × 2 × 2 × 4 × 2 = 256` combinations. `research/execution_safety.py`
(offline, mirrors Phase 21's `research/decision_benchmarks.py` precedent)
enumerates **all 256** and asserts every Section-12 refusal invariant plus
the complete positive characterization (fail-closed both directions), and
separately enumerates all risk-increasing / safety-removing mutations to
assert none ever flips a refusal into an allow (Section-10 metamorphic
properties). **Zero counterexamples** across the whole space -- an
exhaustive proof, not a sample.

### Crash-window analysis (W1-W7)

Because no executor is wired, **every window W1-W7 that involves an
external effect is currently UNREACHABLE** -- there is no external call to
crash before/after. This ADR records the desired behavior for when an
executor is eventually wired (a future phase), so the analysis is not
lost:

| Window | Reachable today | Desired behavior once wired |
|---|---|---|
| W1 intent persisted, crash before external call | No | On restart: journal shows unresolved intent → `REFUSED_UNRESOLVED_INTENT`; requires human/evidence resolution before retry |
| W2 definite pre-effect failure, crash before local persist | No | Safe to retry (prior = `DEFINITELY_NOT_SUBMITTED`), per policy |
| W3 submission succeeds, crash before recording | No | Reconstructed prior is unresolved-intent → not auto-retried; needs evidence it did/didn't land |
| W4 timeout, remote may/may not have submitted | No | `OUTCOME_UNCERTAIN` → `retry_allowed = false`, always -- the core reason `OUTCOME_UNCERTAIN` exists |
| W5 success recorded, notification fails | No | Notification is best-effort (ADR-0005/0040); never rolls back business state, never resubmits (I11) |
| W6 submit ok, app-store write fails, journal ok | No | Reconstruct from journal → unresolved/uncertain → no blind retry |
| W7 submit ok, journal write fails, app-store ok | No | ADR-0048 prior-attempt guard still blocks a duplicate; journal gap is a forensic loss, not a duplication risk |

**Write-ahead `EXECUTION_INTENT`** (Section 7): justified *in principle*
for W1/W3/W4 (a durable intent written before the external call lets
reconstruction detect an interrupted irreversible action), but **not
implemented now** -- there is no external call to precede, so writing
intent ahead of nothing would be speculative. It is specified here as the
first thing a future executor-wiring phase must add, alongside a real
acknowledgement classifier.

## Alternatives rejected

- **Option A/B (wire an executor, wholly or partially):** rejected -- no
  executor has a deterministic acknowledgement model (browser =
  no-exception-means-success; email = draft-only; direct API = dead per
  ADR-0027), so none can safely perform an irreversible action; wiring any
  would newly reach crash windows W1-W7 with no ack classifier to resolve
  them.
- **Option D (proof/tests/docs only, no wiring):** rejected as slightly
  under-delivering on rule 30 -- the boundary should be *live* on the real
  reachable path (so it is exercised and its integration point is fixed),
  not shelfware, even though it currently always refuses.
- **A first-class runtime policy *registry* / plugin system:** rejected as
  premature -- a deterministic `resolve_source_policy` function with a
  named, auditable source→policy mapping is sufficient at this scale; a
  registry would be abstraction without a second consumer.

## Consequences

- New pure module `domain/execution.py` (stdlib only; domain-purity
  contract verified -- uses `hashlib`, already on the allowlist).
- New offline `research/execution_safety.py` + `tests/research/
  test_execution_safety.py`: the 256-point exhaustive invariant and
  metamorphic proofs.
- New `tests/domain/test_execution.py` (Families A-D: ack mapping, retry
  admissibility, artifact-digest integrity/order-invariance, policy
  resolution, per-reason refusals, the structural I16-I19 proof).
- New `tests/test_execution_boundary_wiring.py` (Family F: the confirmed
  apply path refuses real execution with `REFUSED_NO_EXECUTOR`; structural
  proofs that `executor_available=True` appears nowhere in `cli.py`, that
  there is exactly one boundary call site, and that no `Applicator` is
  constructed in the composition root -- I15/I20/no-bypass).
- `cli.py`: `_apply_pipeline` computes the boundary decision after
  confirmation, journals `EXECUTION_REFUSED` with the reason, and prints
  it. Exit codes, external effects, and the "Nothing was actually sent"
  outcome are **unchanged** (the Phase 23 happy-path journal test was
  updated to include the new `EXECUTION_REFUSED` event). A fail-closed
  `RuntimeError` guard covers the currently-unreachable `allowed` branch,
  so a future edit enabling execution cannot silently fall through without
  wiring a real executor.
- **Interaction with ADR-0048:** composed, not replaced -- the boundary's
  `prior_outcome` factor is the finer-grained, submission-outcome-typed
  successor to `prior_attempt_status()`'s coarse "some non-rejected
  attempt exists." ADR-0048's guard still runs pre-tailoring and is proven
  still active.
- **Interaction with ADR-0049:** the boundary emits an `EXECUTION_REFUSED`
  event into the ADR-0049 journal, and `journal_has_unresolved_intent` is
  the factor by which a future reconstruction feeds interrupted-intent
  state back into the permission decision.

## Limitations (stated honestly)

- No executor is wired; **no claim of exactly-once execution,
  transactional submission, or guaranteed duplicate prevention is made** --
  those require provider-side idempotency keys/receipts this project does
  not have (RQ20).
- The acknowledgement classifier is specified (the `AckClass` →
  `SubmissionOutcome` law) but not fed by any real executor yet.
- `artifact_matches` and `journal_has_unresolved_intent` are consumed as
  verdicts; the code that *computes* them from a live executor/journal is
  future work, gated behind this same boundary.

## Zero-cost / dependency / safety impact

Zero cost, zero network, zero new dependency, zero live LLM/browser/email
calls. No production external behavior changed; `apply` and `auto` remain
incapable of submitting. Truthfulness, Promptfoo validation, confirmation,
ADR-0048 idempotency, and manual-only source policy are all preserved and
tested-still-active.
