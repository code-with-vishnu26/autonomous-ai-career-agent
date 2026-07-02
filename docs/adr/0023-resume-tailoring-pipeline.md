# ADR-0023: The resume-tailoring pipeline — composition boundary and the `rejected` status

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0003](0003-truthfulness-gate.md) (generator/gate
  split), [ADR-0005](0005-event-bus.md) (events notify, they do not gate),
  [ADR-0018](0018-submission-safety.md) (`SubmittableApplication`, the
  profile-staleness gap), [ADR-0021](0021-email-tier-draft-only.md) (the
  `paused_for_human` dual-meaning precedent this ADR follows for `rejected`),
  [ADR-0022](0022-resume-generator.md) (`ResumeGenerator`, `ContentDrafter`)

## Context

Phase 8a built and proved `ResumeGenerator` and `TruthfulnessGate`
independently. Nothing yet composes them into one walkable path from a real
`Opportunity` to a submittable application. Before writing that composition,
three questions needed real answers, not assumptions: what `Application.status`
a gate-rejected draft gets, how a rejection is surfaced, and — the one that
actually shapes the slice — where composition stops.

## Problem

How does an `Opportunity` + `MasterProfile` become an audited `Application`
and (when approved) a `SubmittableApplication`, without introducing a status
ambiguity, inventing new event vocabulary the project already has unused, or
compounding "first real generation-to-submission wiring" with "first real
confirmation flow against real generated content" in the same slice?

## Decision

### Scope boundary: stop at `SubmittableApplication`, never call `Applicator`

`ResumeTailoringPipeline.run()` (`agents/resume/pipeline.py`) produces an
`Application` (always) and a `SubmittableApplication` (only if approved). It
does not call `Applicator.prepare()`/`submit()`. Producing a
`SubmittableApplication` is pure data assembly — no network I/O, no human
confirmation required. Actually invoking a tier is a categorically different
action: it requires selecting which tier applies (ADR-0019's still-unbuilt
multi-tier selection beyond the single-adapter Tier 1 case) and obtaining a
real `HumanConfirmation`. Folding both into one slice would mean the first
time generation-to-submission is wired end to end is *also* the first time a
confirmation flow gets exercised against real generated content — two new
risk surfaces at once, exactly the compounding pattern this project has
consistently split apart (7a before 7b3, 8a before this ADR's own slice).
Pinned by a canary test checking the module's actual AST imports (not its
prose, which necessarily names `Applicator` to explain the boundary) for
neither `Applicator` nor `ATSAdapter`.

### `Application.status="rejected"`, distinct from `"failed"`

Considered leaving a gate-rejected draft's `Application.status` as
`"failed"` (already in the `Literal`, arguably "the attempt failed at
gating"). Rejected: `"failed"` currently means a submission attempt was
made through a tier and did not succeed — a real-world event, potentially
worth retrying via a different tier. A gate rejection never reached a
submission attempt at all — it is a content problem, where retrying via a
different tier accomplishes nothing until the resume itself is fixed. These
are two different events that would happen to share one status word.
Collapsing them would force every future consumer (a dashboard, a retry
policy, the Learning engine) to re-derive the distinction by also inspecting
`resume.truthfulness.approved` — the same "should-be-structural guarantee
left to inference" pattern this project has refused everywhere else. A new
literal, `"rejected"`, is added to `Application.status`
(`domain/models.py`) — a small, additive model change, the same shape as
adding `canonical_company` (ADR-0014) or `provenance` (ADR-0012) was, not a
redesign.

This is a different call than ADR-0021's `paused_for_human` decision, on
purpose: there, a browser-tier pause and an email-tier pause were both
genuinely "paused, waiting on a human" — the distinction was worth
documenting but not worth a new literal, since both really are the same
kind of event with different resumability. Here, a gate rejection and a
submission failure are not two flavors of the same event; they are
different events that happen to currently share a field. That difference is
what justifies a new literal in one case and only documentation in the
other — the two ADRs reach different conclusions from a genuinely different
shape of ambiguity, not an inconsistent standard.

### Rejections and approvals are surfaced via the two events already defined for this, unused since Phase 2

`ResumeTailored` and `TruthfulnessRejected` (`core/events.py`) have existed
since Phase 2 and were never emitted — no orchestration layer existed to
emit them until now. Same reuse-before-invention pattern as
`HumanActionRequired` sitting dormant until 7b3/7b4. `ResumeTailoringPipeline`
publishes `ResumeTailored` on approval and `TruthfulnessRejected` (carrying
`rejection_count`) on rejection, via the existing `EventBus`. Consistent
with ADR-0005's amendment: events notify, they do not gate — the pipeline's
own control flow (not a subscriber) is what determines `Application.status`
and whether a `SubmittableApplication` is produced; publishing is a
side-effect for observers, never load-bearing for correctness.

### Precondition failures propagate; the pipeline does not swallow them

`MissingSummaryError` (ADR-0022) and any other exception the generator or
gate raise propagate out of `run()` uncaught, and no event is published.
This is composition, not a resilience layer — a precondition failure (an
incomplete profile) is the human's problem to fix, not something to paper
over with a partial or fabricated result.

### On-demand only, confirmed against the profile-staleness trigger

`ResumeTailoringPipeline.run()` takes an explicit `Opportunity`/`MasterProfile`
pair per call; it does not scan, select, schedule, or run recurringly. The
profile-staleness gap (ADR-0018) and the send-confirmation gap (ADR-0021)
are both tied to "before any scheduled/autonomous run" — this slice
introduces no scheduling or autonomy, so neither trigger fires. Stated here
affirmatively rather than assumed to still hold from two phases prior.

## Alternatives considered

- **Call `Applicator.prepare()` at the end of `run()`, stopping short of
  `submit()`.** Rejected: still couples tier/adapter selection logic (not
  yet designed beyond the single-adapter Tier 1 case) into a slice framed as
  pure composition; better to leave that decision to its own pre-brief.
- **Reuse `"failed"` for gate-rejected drafts.** Rejected: overloads a field
  to mean two different things, forcing every consumer to re-derive the
  distinction from a side channel.
- **A new `HumanActionRequired`-style event for rejection instead of
  `TruthfulnessRejected`.** Rejected: `TruthfulnessRejected` already exists,
  already carries the right field (`rejection_count`), and was purpose-built
  for exactly this in Phase 2 — inventing a second mechanism would be
  needless duplication.
- **Catching and converting generator/gate exceptions into a rejected
  `Application` instead of propagating them.** Rejected: a precondition
  failure (e.g. no profile summary) is not the same kind of event as a
  content rejection; collapsing them would hide an actionable fix behind a
  result that looks like ordinary gate output.

## Trade-offs

- **(+)** The composition is provably scoped (canary-checked, not just
  documented); `Application.status` stays unambiguous for every future
  consumer; existing event vocabulary is reused rather than duplicated;
  precondition failures stay loud.
- **(−)** `Application.status`'s `Literal` grows by one value — a small,
  permanent surface every future switch/match over status must account for
  (mitigated: none currently exists, checked before this change). The
  pipeline is deliberately incomplete on its own — it cannot yet actually
  submit anything, which is correct scoping but means "the loop is closed"
  is still one more slice away.

## Consequences

- `domain/models.py`: `Application.status` gains `"rejected"` (additive).
- `agents/resume/pipeline.py` (new): `ResumeTailoringPipeline`,
  `ResumeTailoringResult`.
- `ResumeTailored`/`TruthfulnessRejected` are no longer dormant — any future
  subscriber (a dashboard, structured logging) can now rely on them actually
  firing.
- The next slice (not this one) wires `ResumeTailoringResult.submittable`
  into a real `Applicator` call, including tier selection and obtaining a
  genuine `HumanConfirmation` from a person.

## Future revisit criteria

Revisit if:

- The next slice designs tier selection and confirmation-obtaining for the
  `Applicator` wiring this ADR deliberately deferred.
- A future status-consuming component (dashboard, Learning engine) finds
  `"rejected"` insufficiently granular (e.g. wanting to distinguish
  structural rejections like `skill_not_found` from judged ones) — that is
  a `RejectionReason.category`-level distinction already available on the
  resume, not necessarily a further `Application.status` split.
- Regenerate-with-feedback (deferred in ADR-0022) is designed — it would
  most naturally consume a `"rejected"` `Application` as its trigger.
