# ADR-0022: ResumeGenerator — structural summary, narrow drafting port, no self-verification

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0003](0003-truthfulness-gate.md) (generator/gate
  split), [ADR-0011](0011-structured-tailored-content.md) (structured
  tailored content), [ADR-0016](0016-truthfulness-gate-verification.md)
  (Case #6's structural-guarantee precedent; the `summary` gap this ADR
  closes; `ClaimVerifier`'s cost-cascade exemption, distinguished here)

## Context

`ResumeGenerator` has existed as an unimplemented Phase 2 Protocol since the
beginning — every phase since Phase 5 has been gating and submitting content
the system could not yet produce on its own, only hand-authored test
fixtures. ADR-0016 explicitly left `summary` (free-text) generation and
verification out of scope, coupling Phase 8 to resolve it: `ResumeGenerator`
"must treat `summary` conservatively... until this gap closes, or `summary`
verification must land before Phase 8 ships." This phase decides that.

## Problem

How does `ResumeGenerator` produce a real, LLM-tailored draft without either
(a) reopening the `summary` fabrication risk ADR-0016 deferred, or (b)
requiring a second verification subsystem to be built first?

## Decision

### `summary` sourced read-only from `profile.basics.summary`, never drafted

Same move as `TailoredWorkEntry` having no date fields (ADR-0016's Case #6
correction): rather than building `summary` verification, the generator is
never given write access to the field at all.
[`DraftedTailoring`](../../src/career_agent/domain/models.py) — the type an
LLM-backed drafter is allowed to produce — has no `summary` field.
`LLMResumeGenerator` (`agents/resume/generator.py`) sources `summary`
directly from `profile.basics.summary` and assembles the full
`TailoredContent` itself; the drafter is never asked for one and has no
field to put one in even if it tried. Pinned by a canary test
(`test_drafted_tailoring_cannot_carry_a_summary_at_all`), verified to bite
the same way every guardrail in this project has been.

### A missing `profile.basics.summary` is a loud rejection, not a derived fallback

Considered a structurally-derived fallback (e.g. `"{name} — {most recent
position} at {most recent company}"`) — every token would trace to a real
field, so it would be zero-invention. Rejected anyway: it would produce an
obviously templated, low-quality one-liner sitting at the top of an
otherwise carefully tailored resume. That is not a truthfulness failure, but
this project treats "technically fine, quietly worse than what the user
would actually want" as a failure mode in its own right — the same shape as
the 4c search-hit-confidence problem (ADR-0015). `LLMResumeGenerator.tailor()`
raises `MissingSummaryError` before the drafter is ever called if
`profile.basics.summary` is empty or whitespace-only (proven by an empty
drafter call log, not just an exception) — thirty seconds of user friction
once, preferred over a silently degraded application every time.

### `ContentDrafter`: narrow port, not permanently cost-cascade-exempt

Same shape as `ClaimVerifier` (ADR-0016) — a single, narrow capability
(`draft(opportunity, profile) -> DraftedTailoring`), not the general
Haiku→Sonnet→Opus cascade client the architecture still describes as future
work. Unlike `ClaimVerifier`, this port is **not** permanently exempted from
future cost-cascade routing. The asymmetry that earned `ClaimVerifier` its
exemption was specific: a false-approve on *verification* is catastrophic
and unrecoverable, because the gate is the last line of defense. A
false-approve on *tailoring* — the drafter selecting or phrasing something
ungrounded — is recoverable, because the independent gate catches it
downstream regardless of which model drafted it. Re-deriving the reasoning
for this new, structurally similar but risk-different case (rather than
copying ADR-0016's conclusion by rote) is what justifies treating it
differently: `AnthropicContentDrafter` pins a single capable model
(`claude-opus-4-8`) for this phase, with cascade tiering named as explicit,
undecided future work, not ruled out.

### No self-verification, no auto-retry-on-rejection

`LLMResumeGenerator` does not filter, validate, or pre-screen the drafter's
output against the profile before returning it — doing so would blur the
ADR-0003 split (a generator must never be positioned to approve its own
output, even partially). The gate is the sole, independent backstop,
proven in this phase by feeding real generator output — not hand-authored
fixtures — into the real `LLMTruthfulnessGate` for the first time
(`tests/agents/test_generator_gate_integration.py`): an honest draft
approves, a hallucinated skill is blocked structurally, and a hallucinated
`source_entry_id` is blocked as `employer_mismatch` — the same categories
Phase 5's matrix already proved, now exercised through the actual seam
between two independently-built components instead of only against
fixtures authored to hit known failure shapes. A draft the gate blocks is
not automatically regenerated against the rejection feedback; that is
separate, named future work (regenerate-with-feedback), kept out for the
same "one problem at a time" reason `summary` was kept out of Phase 5.

**A meaningful data point from this integration, worth recording rather
than letting pass as just another passing test:** the unknown-`source_entry_id`
case required **zero new gate logic**. The `employer_mismatch` check that
catches it was written in Phase 5, against hand-authored adversarial
fixtures, months before `ResumeGenerator` existed — and it caught a
fabrication from a producer it was never tested against, with no
special-casing added for generator output. That is stronger evidence than
the Phase 5 matrix alone could provide that the gate is a genuine,
general-purpose mechanism rather than something implicitly shaped to its
own test suite's assumptions. It generalized to a new caller on first
contact. Worth weighting this when deciding how much independent scrutiny
future gate-adjacent components need — the gate has now demonstrated it
doesn't have a blind spot specific to content the system itself produces.

### Prompt versioning: tracked, but not a required field on every draft

`RESUME_DRAFT_PROMPT_VERSION` is a git-tracked constant (`llm/prompts.py`),
the same mechanism as the gate's prompt version — but unlike
`TruthfulnessResult.prompt_version`, it is **not** a required field on every
`TailoredResumeDraft`. A considered scoping choice: a verdict is an
authoritative, audited record whose exact reproducibility matters (ADR-0016);
a draft is not — the gate independently re-verifies every claim in it
regardless of which prompt drafted it, so per-instance provenance carries
materially less weight here.

### Scope: 8a is generation + gate wiring only, not submission wiring

This phase produces and gates a real `TailoredResume`; it does not wire
`ResumeGenerator` output into `SubmittableApplication`/`Applicator`. Same
sequencing logic as 7a proving safety machinery before 7b3 added a new tier:
8a is the first time the gate faces content it was not hand-authored by the
project's own reviewers to hit a specific known failure mode — that friction
belongs contained here, with nothing in the highest-consequence part of the
system (real submission, 8b) depending on it working correctly on the first
attempt.

## Alternatives considered

- **Build `summary` verification now instead of removing write access.**
  Rejected: solves a harder problem (verifying arbitrary prose) than the one
  this phase needs to solve, and ADR-0016 already flagged the structural
  route as preferred wherever available.
- **A structurally-derived `summary` fallback when the profile field is
  empty.** Rejected: zero-invention but quality-degrading; this project has
  consistently treated "quietly worse than what the user wants" as its own
  failure category (4c precedent), not just truthfulness failures.
- **Copying `ClaimVerifier`'s permanent cascade exemption onto `ContentDrafter`.**
  Rejected: the exemption's justification (unrecoverable false-approve) does
  not hold here (the gate recovers a bad draft); applying it anyway would be
  precedent-by-rote, not precedent-by-reasoning.
- **Auto-retry-on-rejection in this slice.** Rejected as a second, separable
  problem layered onto the first; named future work instead.
- **Requiring `prompt_version` on every `TailoredResumeDraft`, mirroring the
  gate.** Rejected: a draft isn't an audited record the way a verdict is;
  the gate's independent re-verification is what makes per-draft prompt
  provenance lower-stakes here.

## Trade-offs

- **(+)** `summary` fabrication is structurally impossible, not merely
  policy; a missing summary fails loud and fast rather than degrading
  silently; the generator/gate seam is proven with real component code, not
  assumed to compose correctly; the port is scoped to the risk it actually
  carries, not a heavier one borrowed from a different component.
- **(−)** Users with an empty `basics.summary` cannot tailor a resume until
  they fill it in — friction accepted deliberately. `ContentDrafter` is not
  yet cost-optimized (single pinned model, no cascade). No auto-retry on a
  blocked draft — a rejected attempt requires a person to act, not the
  system retrying automatically.

## Consequences

- `domain/models.py`: `DraftedTailoring` added (additive); `TailoredContent`
  unchanged.
- `core/interfaces.py`: `ContentDrafter` added (additive); `ResumeGenerator`
  unchanged from Phase 2.
- `agents/resume/generator.py` (new): `LLMResumeGenerator`,
  `MissingSummaryError`.
- `llm/content_drafter.py` (new): `AnthropicContentDrafter` — untestable
  live in this sandbox, same disclosure as `AnthropicClaimVerifier`; not
  gated by promptfoo before wiring, unlike `ClaimVerifier`, since the
  consequence of a bad draft is recoverable by the gate rather than
  catastrophic (a lighter validation bar is itself a considered choice, not
  an oversight — a future live-validation pass before production use is
  still recommended, just not made a hard merge gate the way promptfoo is
  for the verifier).
- `llm/prompts.py`: `RESUME_DRAFT_PROMPT`/`RESUME_DRAFT_PROMPT_VERSION` added.
- Phase 8b (wiring generation into real submission) is explicitly deferred
  to a follow-up slice.

## Future revisit criteria

Revisit if:

- Cascade tiering is designed for `ContentDrafter` — this ADR only rules out
  copying `ClaimVerifier`'s *permanent* exemption, it does not decide
  tiering policy.
- Regenerate-with-feedback (auto-retry on a blocked draft) is designed.
- `summary` verification is eventually built anyway (e.g. because users want
  LLM-assisted summary editing) — at that point the read-only-sourcing
  design here should be explicitly reconsidered, not just extended around.
- Real-model validation (a promptfoo-equivalent suite) for
  `AnthropicContentDrafter` is judged necessary before wider use, given
  real-world experience with draft quality.
