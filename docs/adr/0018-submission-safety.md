# ADR-0018: Submission safety — structural approval, confirmation-token binding, and verifier isolation

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0003](0003-truthfulness-gate.md) (the gate `SubmittableApplication`
  enforces), [ADR-0008](0008-human-in-the-loop.md) (human-in-the-loop, restated
  concretely here), [ADR-0010](0010-hybrid-application-strategy.md) (the tiered
  applicator this ADR's `TieredApplicator` begins implementing), [ADR-0011](0011-structured-tailored-content.md)
  (`TailoredResumeDraft`/`TailoredResume`, the precedent this ADR's
  `SubmittableApplication` split follows), [ADR-0016](0016-truthfulness-gate-verification.md)
  (`ClaimVerifier`/`AnthropicClaimVerifier`, isolated further here)

## Context

Every phase through Phase 6 reads the world — discovers postings, extracts
facts, verifies claims. Phase 7 is the first phase that *acts* on it:
submitting a real application to a real company through a real ATS. That is
qualitatively different: everything built so far has been tested in
isolation, and this is where the truthfulness gate has to actually block a
real submission, not just return `approved=False` inside a unit test. Being
wrong before Phase 7 cost a bad test or a wasted review cycle; being wrong
here can mean a real company receiving a bad application, or the user's
account getting flagged. The design had to answer four things before any
code: whether the gate is a hard gate at the point of action (not just a
component that exists), what "submit" means while `AnthropicClaimVerifier`
remains unverified live, the network/ToS reality for these hosts, and where
the human sits in the loop for the one irreversible action in this system.

## Problem

How does the submission code path become structurally incapable of firing
without an approved `TruthfulnessResult`, an explicit human confirmation
bound to the exact thing being sent, and a wall between it and the
not-yet-live-verified `ClaimVerifier` — while staying buildable and testable
in a sandbox that cannot reach any of these hosts?

## Decision

### 1. `SubmittableApplication`: the same "impossible to construct otherwise" discipline, one step downstream

`Application.resume: TailoredResume` always carries a `TruthfulnessResult`,
including a rejected one (Phase 5's audit commitment: a blocked attempt
stays visible). Nothing about `Application` itself prevents it from being
handed to a submission method with `resume.truthfulness.approved is False` —
that would have been enforced by a runtime `if` in orchestration code, the
exact "probabilistic discipline applied to a should-be-structural guarantee"
failure mode this project has rejected everywhere else.

`SubmittableApplication(application: Application)` is a new domain type
(`domain/models.py`) with a Pydantic `model_validator(mode="after")` that
raises `ValidationError` if `application.resume.truthfulness.approved` is not
`True`. The validator runs on **every** construction path — there is no
factory-only enforcement to accidentally bypass by constructing the model
directly. `to_submittable(application)` is a named, readable wrapper around
the same call, not a second, looser way in (tested: it fails identically to
direct construction on a rejected resume). `Applicator.prepare`/`.submit` and
`ATSAdapter.submit` (`core/interfaces.py`) now take `SubmittableApplication`,
not `Application` — the same shape-split precedent as `TailoredResumeDraft`
vs `TailoredResume` (ADR-0011), applied to submission instead of tailoring.

**Named, out-of-scope gap, with a trigger, not left floating:** `SubmittableApplication`
does not re-check whether `profile_version` is still current at submission
time — a resume verified against a profile the user has since edited is not
re-verified here. Low risk for a one-off manual tailor-and-submit sitting;
real risk once the pipeline runs on a schedule or autonomously, discovering
today and submitting days later against a since-edited profile. **This gap
must close before any scheduled or autonomous run of the apply pipeline is
built** — whichever future phase introduces that (Planner scheduling / an
autonomy setting) must either close this gap first or treat it as a blocking
precondition, the same way the `summary`-verification gap (ADR-0016) is tied
to Phase 8's `ResumeGenerator`.

### 2. `AnthropicClaimVerifier` isolation: checked mechanically, not trusted on word

The promptfoo suite (ADR-0016) remains the hard gate before `AnthropicClaimVerifier`
touches any real submission path — that has not changed, and has not
happened. What's new: this is no longer just a claim in a PR description. A
fourth import-linter contract (`pyproject.toml`) forbids `career_agent.agents`,
`career_agent.core`, `career_agent.plugins`, and `career_agent.storage` from
importing `career_agent.llm.claim_verifier` at all — the same enforcement
pattern already proven for `plugins` never importing `core.config` directly.
Verified the same way that contract was: by injecting a real import of
`AnthropicClaimVerifier` into `agents/apply/applicator.py`, confirming
`lint-imports` reports the contract broken, then reverting. Phase 7's
composition root and all its tests are 100% `FakeClaimVerifier`-backed
(`LLMTruthfulnessGate(FakeClaimVerifier(...))`); wiring the real verifier in
is a deliberate, separate, later action gated on a live promptfoo run, not
something that can happen by accident because the two modules sit near each
other in the dependency graph.

### 3. Network reality: offline-fixture-first, same discipline as every prior ATS-adjacent phase, higher stakes

Direct ATS submission endpoints, driven-browser targets, and SMTP (Gmail) are
real external hosts, blocked by this sandbox's network policy the same way
discovery-side APIs were in Phase 4. This slice's `TieredApplicator` and
`ATSAdapter` are built and tested exclusively against `FakeATSAdapter`
(`tests/_fakes.py`) — no live network call is possible or attempted here.
The difference from Phase 4's version of this discipline is **consequence,
not testability**: a bad fixture assumption in a discovery source produces a
bad database record; a bad fixture assumption in a submission adapter
produces a real, wrong submission the first time it runs live. Accordingly,
`FakeATSAdapter` models not just a clean success path but a real ATS-side
failure (`SubmissionError`, carrying a `category` — duplicate submission,
rate limit, malformed payload) as a distinct, tested outcome
(`ApplicationFailed`), not just a happy-path 200. Live submission is
validated only on the user's own machine, deliberately, later.

### 4. `prepare()`/`submit(preview, confirmation)`: confirmation as a type-level guarantee, not a workflow convention

`Applicator.apply(application) -> Event` (Phase 2's original single-method
shape) is replaced with two methods:

- `prepare(application: SubmittableApplication) -> SubmissionPreview` —
  assembles exactly what would be sent (tier, target, rendered content); no
  network I/O; cannot itself submit.
- `submit(preview: SubmissionPreview, confirmation: HumanConfirmation) -> Event`
  — the only method that performs the real submission.

`HumanConfirmation` is not a boolean. It carries `preview_token` (must equal
`SubmissionPreview.preview_token` exactly), `confirmed_by`, and
`confirmed_at` — naming the specific preview being authorized, not "a
submission" in general. `TieredApplicator.submit` (`agents/apply/applicator.py`)
enforces this by construction: an unknown token, a preview that doesn't match
what `prepare()` issued, or a confirmation naming a different token all
`raise` before the `ATSAdapter` is ever reached (tested: the adapter's call
log is asserted empty in these cases, not just that the result is an error).
Tokens are one-shot — consumed before the adapter is called, so the same
`(preview, confirmation)` pair cannot be replayed to submit twice. There is
no `apply()` on the new `Applicator` Protocol that performs both steps
internally; that would put the confirmation requirement behind something
orchestration code could no longer see or skip, undoing the point of the
split. No auto-confirm path is built in this phase — a future,
separately-approved autonomy setting per ADR-0008's "user-defined controls"
note may add one; it does not exist by default.

### Scope of this slice: one tier, no fallback, named not silently dropped

`TieredApplicator` wraps exactly one injected `ATSAdapter` (Tier 1, direct
ATS API) and always targets it. Multi-tier fallback (browser, email) and
company/ATS-kind resolution (`Opportunity` → which `ATSAdapter` applies) are
**not** built in this slice. This mirrors Phase 4's sub-slicing precedent
(4a: one real source first, proving the contract, before 4b/4c added the
rest) — the safety machinery (structural approval, confirmation-token
binding, verifier isolation) is the thing that had to be proven correct
first; tier selection is real, separate work ADR-0010 itself already flags
as possibly warranting its own future ADR.

## Alternatives considered

- **Enforce approval with a runtime check in orchestration code instead of a
  new type.** Rejected: exactly the probabilistic-discipline-on-a-structural-
  guarantee failure mode this project has avoided everywhere else (see
  `provenance`, `canonical_company`, `TailoredResumeDraft`/`TailoredResume`).
- **A single `apply()` method with an optional `auto_confirm` flag.** Rejected:
  a flag defaulting to `False` is still something a caller can flip or
  forget; a required, token-bound argument on a method that cannot be
  reached without it is a stronger guarantee than a default.
- **Re-checking profile staleness in this slice.** Rejected as premature
  scope for now — real, separate problem from approval enforcement — but
  tied to a concrete future trigger (any scheduled/autonomous run) rather
  than left an untethered "someday" note.
- **Building all three tiers in this slice.** Rejected: the safety machinery
  needed to be provably correct on its own before tier-selection complexity
  (ADR-0010's own flagged future concern) is layered on top; matches the
  Phase 4a precedent of one real implementation before breadth.

## Trade-offs

- **(+)** Submitting an unapproved resume, an unconfirmed preview, or a
  replayed confirmation are all type-level impossible, not merely tested-
  against; `AnthropicClaimVerifier`'s isolation from orchestration is
  mechanically checked (import-linter), not just claimed; fixtures model
  real ATS-side failure, not only the happy path.
- **(−)** `Applicator`'s two-method split is a breaking change to the Phase 2
  `apply()` shape (no external caller existed yet, so no migration cost
  beyond this repo's own tests). This slice cannot submit through more than
  one tier or fall back on failure — real capability deferred, not silently
  dropped. Profile-staleness re-verification remains an open gap until its
  named trigger phase closes it.

## Consequences

- `core/interfaces.py`: `Applicator.apply` removed in favor of `prepare`/
  `submit`; `ATSAdapter.submit` re-typed to `SubmittableApplication`.
- `domain/models.py`: `SubmittableApplication`, `to_submittable`,
  `SubmissionPreview`, `HumanConfirmation` added.
- `agents/apply/applicator.py`: `TieredApplicator`, `SubmissionError` (new).
- `pyproject.toml`: a fourth import-linter contract, verified to bite.
- Any future phase adding scheduled or autonomous apply runs must close the
  profile-staleness gap named above first.
- Tier 2 (browser)/Tier 3 (email) and multi-tier fallback/company resolution
  are follow-up sub-slices of Phase 7, not part of this one.

## Future revisit criteria

Revisit if:

- Tier 2/3 and fallback selection are built — `TieredApplicator`'s
  single-adapter constructor will need to become a real tier-selection
  strategy (ADR-0010 already anticipates this may warrant its own ADR).
- The profile-staleness gap's trigger condition (a scheduled/autonomous apply
  run) is reached.
- `AnthropicClaimVerifier` passes promptfoo live and is deliberately wired
  in — at that point the import-linter contract's `forbidden_modules` entry
  is replaced by whatever narrow, explicit wiring point is chosen; it should
  never simply be deleted.
- A real ATS's actual failure-response shapes (once observed live) turn out
  to need more `SubmissionError` categories than duplicate/rate-limit/malformed.
