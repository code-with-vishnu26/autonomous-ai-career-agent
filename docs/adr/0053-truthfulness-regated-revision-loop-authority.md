# ADR-0053: Truthfulness-re-gated revision loop — authority model, and no LLM reviewer (Phase 27)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0034](0034-ats-score-gate.md) (the ATS gate + auto-retailor
  loop that *is* this revision loop), [ADR-0016](0016-truthfulness-gate.md) /
  [ADR-0044](0044-formal-claim-evidence-entailment-and-deterministic-precheck.md)
  (truthfulness authority this must not weaken),
  [ADR-0022](0022-resume-generator.md) (generator: no self-verification),
  [ADR-0052](0052-evidence-grounded-cv-ingestion.md) (Phase 26 trust
  boundary this must not let leak)

## Context

Phase 27's brief asked for a truthfulness-re-gated drafting/revision loop:
Draft → Review → Revise → Truthfulness Gate → ATS Gate → Render, with the
non-negotiable that no reviewer/reviser/LLM/orchestration path may promote
an unsupported claim into an accepted resume.

**A fresh repository audit found this loop already exists and is used
(PRESENT_AND_USED).** `ResumeTailoringPipeline._ats_gate_loop`
(`agents/resume/pipeline.py`, ADR-0034/Phase 10) implements exactly:

1. draft → truthfulness gate → (if approved) render → ATS gate;
2. on ATS fail, retailor (revise) up to `_MAX_ATS_RETRIES = 2`, driven by a
   **SURFACEABLE-only** `AtsGapReport` (the type has no field able to carry
   a GENUINE/fabrication-target gap; the semantic matcher prunes
   false-missing keywords, each verified verbatim against the resume);
3. every retailored draft goes through the **FULL truthfulness gate before
   it is ever ATS-scored** — a truthfulness-rejected retry is never scored,
   consumes the retry, and the loop continues;
4. convergence detection (identical retry stops early);
5. exhaustion/convergence below threshold **fails closed**
   (`AtsScoreBelowThresholdError`), never silently accepting the latest
   draft.

This is already covered by tests (`tests/agents/test_ats_gate_loop.py`
cases A1/B1–B5; `tests/agents/test_truthfulness_gate_hardening.py`).

## Decision (Option A: no new revision subsystem; formalize + prove)

**No LLM reviewer, `ResumeReviewer`, `ResumeReviser`, or new revision
interface is added.** Building one would be a duplicate of the existing
loop (which the brief forbids), would add a prompt-injection surface (the
job description flowing into a reviewer prompt) and an LLM cost per apply,
for marginal value: the reviser's output would still have to pass the same
truthfulness gate, which is precisely what the ATS-driven retailor already
does. Options C (LLM reviewer + bounded reviser), D (multi-provider
debate), and E (variant search) were rejected as unjustified complexity
under this project's evidence-first discipline.

Phase 27 instead (1) records the authority model durably here, and (2)
adds the *composition* invariant tests that were not previously asserted
directly (`tests/agents/test_phase27_revision_authority.py`).

### Authority model (precedence)

```
deterministic Layer-1 precheck reject  ─┐
LLM ClaimVerifier reject                ─┼─►  TRUTHFULNESS REJECTION  (absolute)
                                          │        │  strictly dominates
ATS gap report / "reviewer" advice       │        ▼
(SURFACEABLE keywords only)             ─┘   ATS readiness preference
                                                   │  strictly dominates
                                                   ▼
                                          drafter wording choices
```

- **Truthfulness authority is absolute and non-overridable.** The ATS gap
  report is *advisory only*: it can influence which existing evidence the
  drafter is asked to surface, never establish that a claim is true. A
  truthfulness rejection is never rescored, never bypassed, and a high ATS
  number for an unapproved draft *does not exist* (it is never computed).
- **The drafter/reviser establishes wording, never truth** (ADR-0022: no
  self-verification; the gate is the sole independent backstop).
- **Skills are structural** — a skill not present in `MasterProfile.skills`
  is rejected without a model call, so an ATS-suggested or
  injection-suggested skill the candidate lacks cannot enter an accepted
  resume.
- **Human authority** (`HumanConfirmation`, ADR-0018/0024) sits *after*
  this loop, unchanged and unreachable from it; the loop produces a
  `SubmittableApplication`, never a submission.

### What the composition tests prove (Phase 27's additive contribution)

- **I9 / job-description-is-not-evidence:** `LLMTruthfulnessGate.verify`'s
  signature is `(draft, profile)` — it never receives the opportunity/JD,
  so untrusted JD text is *structurally* unable to reach the ClaimVerifier
  as evidence. The JD influences only drafting wording and ATS relevance.
- **I3 / no verification cache:** the gate recomputes every verdict on
  every `verify()` call, so a revised draft's claims (changed or unchanged)
  are always re-judged; a verdict is never carried over from a prior draft.
  Verification caching was therefore considered and **rejected** (it is not
  needed at this scale and would risk a stale approval).
- **I10/I11 / Phase 26 isolation:** the entire `agents/resume` package has
  no import of `domain.ingestion`/`storage.cv_ingest` and references no
  `FactProposal`/`IngestionDraft` — an UNVERIFIED or REJECTED imported CV
  fact has no path into the revision loop. Only facts promoted into the
  trusted `MasterProfile` (ADR-0052) participate, via the profile the
  pipeline already consumes.
- **I1/I2/I4/I13 / injection end-to-end:** an adversarial JD that makes the
  drafter emit an unsupported skill produces a *rejected* application with
  no submittable output — the injected text authorizes nothing.

## Prompt / Promptfoo / dependency impact

**None.** No truthfulness prompt semantics change, so the prompt version is
**not** bumped (I24 — no ceremony bump) and no Promptfoo artifact is
touched or invalidated (I22/I23 preserved). No new dependency; no LLM or
network call in any test; zero cost. `apply`/`auto`/`discover`,
idempotency (ADR-0048), the execution journal (ADR-0049), and the
execution-safety boundary (ADR-0050) are all unchanged; **no external
submission becomes newly reachable.**

## Consequences

- No production code changed. New tests only
  (`tests/agents/test_phase27_revision_authority.py`): Phase 26 →
  resume-pipeline import isolation; the gate-never-sees-the-JD signature
  proof; the no-verification-cache behavioral proof; and the end-to-end
  injection-rejection test.
- The decision *not* to add an LLM reviewer is now durable and cited, so a
  future phase must justify against this ADR (and, if it ever adds one,
  must route every revised claim through the unchanged truthfulness gate
  and keep the JD out of candidate evidence).

## Limitations / what remains impossible to guarantee

- The drafter's LLM does see the (untrusted) JD, so injection can influence
  *wording*; safety rests entirely on the gate re-judging every output
  claim. This is sound for claim truthfulness but cannot guarantee the JD
  never nudges tone/emphasis — an accepted, truthful resume is still the
  only possible output, but "the JD had zero influence on phrasing" is not
  claimed.
- `max revisions = 2` is retained from ADR-0034 (diminishing returns at
  this project's scale); it is a bound, not an optimum.

## Recommended Phase 28

If richer revision is ever wanted, the safe shape is a *deterministic*
advisory reviewer (reusing `keyword_sensitivity`/the ATS report) emitting a
typed, closed-vocabulary hint set that is filtered to SURFACEABLE-only
*before* revision — never an LLM reviewer with free-form authority — and
still re-gated. Only pursue it if real usage shows the current ATS-driven
retailor leaves a genuine, observed quality gap.
