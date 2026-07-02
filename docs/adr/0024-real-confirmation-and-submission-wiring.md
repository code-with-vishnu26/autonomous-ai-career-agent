# ADR-0024: Real human confirmation and single-tier submission wiring

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0008](0008-human-in-the-loop.md) (human-in-the-loop
  applying, the "explicit confirmation" commitment this ADR finally
  implements), [ADR-0010](0010-hybrid-application-strategy.md) (the tier
  selection this ADR confirms was never actually built), [ADR-0018](0018-submission-safety.md)
  (`SubmittableApplication`, `HumanConfirmation` token binding), [ADR-0019](0019-ats-kind-resolution-and-tier-fallback.md)
  (no cross-tier auto-retry), [ADR-0023](0023-resume-tailoring-pipeline.md)
  (the pipeline this ADR's `SubmissionPipeline` continues)

## Context

By Phase 8b, every structural guarantee in the submission-safety chain —
the truthfulness gate, `SubmittableApplication`, token-bound
`HumanConfirmation` — had been proven, repeatedly, against fakes. No real
human had ever produced a `HumanConfirmation` outside a test fixture. This
phase closes that gap: the first slice where a real confirmation source can
drive a real `Applicator` call.

## Problem

Two real decisions, not composition: (1) does this slice build real
multi-tier selection, given `ATSAdapter`/`BrowserApplicator`/`EmailApplicator`
are three independent `Applicator` implementations with nothing that
chooses between them; and (2) where does a real `HumanConfirmation`
actually come from for the first time — is building that its own deferred
piece of work, or does this slice build it now?

## Decision

### Single-tier this slice; multi-tier selection is confirmed as real, unbuilt, deferred work

Checked before assuming: `TieredApplicator`, `BrowserApplicator`, and
`EmailApplicator` each independently satisfy the `Applicator` Protocol.
There is no fourth component that picks between them — ADR-0010's "tier
selection is an internal strategy this implementation chooses between"
described a component that was never actually built. Building a real
selector (which tier applies to a given `Opportunity`, what "none apply"
means) is genuine design work. This slice stays single-tier:
`SubmissionPipeline` wires against exactly one concrete `Applicator`
(`TieredApplicator`, proven here against an ATS-sourced opportunity) — the
same "prove one path first" discipline as Greenhouse-first (Phase 4a),
Tier-1-only (ADR-0018), and Greenhouse's-form-only (ADR-0020). Multi-tier
selection remains named, deferred, future work.

### Build the real CLI confirmation now — the deferred-external-integration precedent does not transfer

Considered deferring the real confirmation source the same way
`AnthropicClaimVerifier` (ADR-0016) and the real, OAuth-backed
`GmailDraftSink` (ADR-0021) were deferred — narrow the slice, keep the
orchestration generic against an injected port, build the real
implementation later. Rejected on inspection: those two were deferred
because they are **untestable live in this sandbox** — a real network call
to Anthropic or a real OAuth-backed Gmail client cannot be exercised here at
all. A CLI confirmation prompt has no such constraint. It is pure local
stdin/stdout I/O, fully testable in this same sandbox, with zero external
dependency. Deferring it would be a scope-narrowing choice dressed up as the
same kind of forced deferral those two were — and unlike those two, this is
also the **one remaining unexercised link in the entire submission-safety
chain**: every guarantee built through Phase 8 has been proven against
fakes on both sides, never against an actual person answering an actual
prompt. Deferring the one link that has never been exercised, on a
precedent built for a different reason, was judged the wrong trade.

`cli.confirm_submission` (`cli.py`) is built now, deliberately minimal:
displays the `SubmissionPreview`, reads one line from stdin via an injected
`input_fn` (so it is exactly as testable as everything else in this
project, no `input()`-monkeypatching required), and returns a
`HumanConfirmation` **only** for an exact "y"/"yes" (case-insensitive)
answer. Anything else — "n", empty input, garbage — returns `None`. There is
**no default-to-yes path**: silence is treated as refusal, never as
consent. Verified the same way every guardrail in this project has been:
the "no default-to-yes" behavior was broken on purpose (accepting empty
input as an implicit yes), confirmed the test caught it, reverted.

`cli.main()` remains the Phase 1 placeholder. Wiring `confirm_submission`
into a real `career-agent apply <id>` command — argument parsing, loading a
real profile/opportunity from storage — is separate, later work; this ADR
builds the confirmation *function*, not the command.

### `SubmissionPipeline`: prepare, confirm, submit, or abort cleanly

`agents/apply/pipeline.py`'s `SubmissionPipeline` takes any `Applicator`
and any confirmation source matching `Callable[[SubmissionPreview],
HumanConfirmation | None]` — the real `cli.confirm_submission` and a
scripted fake in tests satisfy the exact same shape, so the pipeline itself
never knows or cares which answered. `run()` calls `prepare()`, hands the
preview to `confirm`, and calls `submit()` only if a `HumanConfirmation` was
actually returned. A declined confirmation (`confirm` returns `None`) is a
legitimate, final, non-error outcome — the pipeline returns `None` and
`submit()` is never called, proven the same way as every other refusal in
this project's submission chain: by asserting the underlying adapter's call
log stays empty, not just that no exception was raised.

## Alternatives considered

- **Defer the real CLI confirmation, mirroring `AnthropicClaimVerifier`/
  `GmailDraftSink`.** Rejected: those deferrals were forced by an
  untestable-live-in-sandbox external integration; a local stdin/stdout
  prompt has no such constraint, so the precedent doesn't actually apply.
- **Build real multi-tier selection in this slice, since it's "closing the
  loop."** Rejected: genuine design work (what does "no tier applies" mean,
  how does fallback interact with ADR-0019's no-auto-retry rule) that
  deserves its own pre-brief, not a rider on wiring one real path through.
- **A richer, formatted CLI confirmation UI (colors, a diff view against the
  master profile, etc.).** Rejected as premature — "prove the mechanism,
  not the product," the same discipline as every other first pass in this
  project (the plain-function profile loader, the bare-bones fixture HTML
  form). A real UI is future work once the mechanism is proven.
- **Re-prompting on malformed input instead of aborting cleanly.** Not
  chosen: aborting cleanly is simpler, avoids an unbounded input loop in a
  scripted/non-interactive context, and is one of the two acceptable
  behaviors named when this was scoped; re-prompting can be added later
  without changing the safety guarantee.

## Trade-offs

- **(+)** The submission-safety chain has now been exercised end to end
  against a real confirmation source, not fakes on both sides; the
  "no default-to-yes" guarantee is verified to actually catch a regression,
  not just asserted; the single-tier scope keeps this slice provably small.
- **(−)** `career-agent` still has no real, runnable `apply` command — only
  the confirmation function it will eventually use. Multi-tier selection
  remains unbuilt; an opportunity whose only viable tier isn't
  `TieredApplicator`'s single adapter cannot be submitted through this path
  yet.

## Consequences

- `cli.py`: `confirm_submission` added (real, not a placeholder); `main()`
  unchanged.
- `agents/apply/pipeline.py` (new): `SubmissionPipeline`.
- The next slice that wires a real `apply` command must call
  `confirm_submission`/`SubmissionPipeline` rather than reinventing
  confirmation-obtaining logic.
- Multi-tier selection (choosing between `TieredApplicator`,
  `BrowserApplicator`, `EmailApplicator` for a given opportunity) remains
  unbuilt and is the natural next piece of real design work in this area.

## Future revisit criteria

Revisit if:

- A real multi-tier selector is designed — it must respect ADR-0019's
  no-auto-retry rule (each tier its own `prepare`/confirm/`submit` cycle).
- A real `career-agent apply` command is built, wiring `confirm_submission`
  and `SubmissionPipeline` into an actual CLI argument-parsed entry point.
- Real-world use shows re-prompting on malformed input (rather than
  aborting) is worth the added complexity.
- The confirmation UI needs to become richer than plain stdin/stdout (e.g.
  a TUI or web dashboard) — that is real, separate future work, not an
  extension of this minimal pass.
