# ADR-0026: Real `career-agent apply` command, promptfoo positive enforcement, and stopping before submission

- **Status:** Accepted
- **Date:** 2026-07-03
- **References:** [ADR-0016](0016-truthfulness-gate.md) (the promptfoo suite
  requirement this ADR converts from policy to a positively-checked fact),
  [ADR-0018](0018-submission-safety.md) (`SubmittableApplication`),
  [ADR-0023](0023-resume-tailoring-pipeline.md) (`ResumeTailoringPipeline`,
  composed here), [ADR-0024](0024-real-confirmation-and-submission-wiring.md)
  (`confirm_submission`, `SubmissionPipeline`, and the explicit deferral of
  "wire a real `apply` command" that this ADR now closes)

## Context

By the end of Phase 8, every structural guarantee in this project — the
truthfulness gate, `SubmittableApplication`, token-bound
`HumanConfirmation`, tiered applicators — had been proven repeatedly against
fakes. No real person had ever typed a real command against real data.
`cli.py` exposed only `confirm_submission` (a function) and the Phase 1
placeholder banner; there was no runnable `apply` command at all.

## Problem

Three real design questions, not simple wiring:

1. **How does a person specify which `Opportunity` to apply to?** There is
   no persistent `OpportunityRepository` (only `InMemoryOpportunityRepository`,
   not durable across processes) and no `discover` command that would
   populate one.
2. **Is `AnthropicClaimVerifier` safe to wire into a real path yet?**
   ADR-0016 requires the promptfoo suite to pass on live calls first. That
   requirement existed only as written policy plus an import-linter contract
   that (correctly) leaves `cli.py` unconstrained, since it is the
   composition root — nothing structural stopped a real, unvalidated
   verifier from being wired in at exactly the point it would first matter.
3. **What does this command do with a confirmed application?** No real
   `ATSAdapter` exists anywhere in this codebase (only `FakeATSAdapter`,
   test-only) — a confirmed application has nowhere real to actually be
   sent yet.

## Decision

### Opportunity input: a plain `--opportunity-file` JSON handoff

Rejected building persistent storage or a `discover` command to satisfy
this command's needs (`OpportunitySource`/storage design deserves its own
pre-brief, not a rider on this slice), and rejected re-coupling `apply` to
one specific discovery/source implementation (cuts against the multi-source
architecture the rest of the project maintains). Instead `apply` reads an
`Opportunity` from a plain JSON file via `--opportunity-file`. This is the
narrowest real scope: a future `discover` command can produce this same
file format without either command's internal logic changing, and a future
persistent store can replace the file handoff later the same way — matching
how every other slice in this project has been sequenced.

### The real `ClaimVerifier` is gated by an actual check, not a claim

Rejected a CLI flag a caller types from memory (e.g.
`--i-have-validated-promptfoo`) — that is a claim, not a fact, and is
exactly the kind of unverified self-assertion this project's "check the
evidence, not the claimed verdict" discipline exists to rule out, now
applied to trusting ourselves rather than a URL pattern or a claimed
confidence score.

`llm/promptfoo_gate.py::verify_promptfoo_results(prompt_version,
results_dir)` instead checks an actual results artifact on disk:
`results_dir / f"{prompt_version}.json"`, the shape `promptfoo eval -o
<file>` writes. It raises `PromptfooNotValidatedError` unless the file
exists, parses, and records `successes > 0` and `failures == 0`. The
filename is keyed to the exact prompt version being validated
(`TRUTHFULNESS_GATE_PROMPT_VERSION`) — a stale pass recorded under a
since-changed prompt version has a different filename and will not be
found, so it can never silently count as a still-valid pass. `zero
successes, zero failures` (an empty/no-op run) is also rejected — a
promptfoo suite that ran nothing is not a suite that passed.

`run_apply_command` calls this before constructing
`AnthropicContentDrafter`/`AnthropicClaimVerifier` (in that order, after the
`ANTHROPIC_API_KEY` presence check but before any real Anthropic client is
built) — refusing to proceed leaves no path to a real, unvalidated
`AnthropicClaimVerifier` being exercised against a live opportunity.
Verified this ordering actually bites: temporarily removed the
`verify_promptfoo_results` call from `run_apply_command`, re-ran
`test_promptfoo_not_validated_blocks_even_with_a_valid_api_key`, and
confirmed it failed with a real `anthropic.AuthenticationError` (an actual
attempted network call, using the test's deliberately-fake API key) rather
than the promptfoo error the check is supposed to raise first — proving the
check is genuinely load-bearing at this exact ordering point, not merely
present. Reverted after confirming.

### Stop at confirmation; name submission as separate, future work

Considered building a real Greenhouse `ATSAdapter` now to give a confirmed
application somewhere real to go. Rejected (explicit choice, asked and
answered directly): that is its own real integration slice — real form
discovery/field-mapping/submission against a live ATS — and deserves its
own pre-brief, not a rider on "make the CLI runnable." `apply` tailors,
gates, renders, and asks for a real confirmation, then stops: on a
confirmed "yes" it prints that no real ATS adapter is wired in yet and that
nothing was actually sent, rather than simulating or faking a submission.
`_apply_pipeline` deliberately never imports or calls any `Applicator`.

### `main()` now takes an explicit `argv`

Discovered as a real regression, not anticipated: once `main()` began
calling `argparse.ArgumentParser().parse_args()` with no arguments, the
pre-existing `test_cli_entrypoint_runs` failed under pytest, because
`parse_args()` with no explicit `argv` reads the real process's
`sys.argv` — under pytest that is pytest's own CLI flags (`-q`, etc.), not
an empty argument list. Fixed with the same dependency-injection discipline
used everywhere else in this project (`input_fn` for `confirm_submission`):
`main(argv: list[str] | None = None)` passes `argv` through to
`parse_args(argv)`; `argv=None` still correctly falls back to real
`sys.argv[1:]` for the actual `career-agent` entry point, but any
programmatic caller (tests) must now pass an explicit list. Verified this
guarantee bites: temporarily reverted `parse_args(argv)` to
`parse_args()`, re-ran `test_cli_entrypoint_runs`, confirmed it failed with
`SystemExit: 2` (`argument command: invalid choice`, parsing the test
runner's own arguments), reverted.

### Stays on-demand; no scheduling

`apply` is a single-run, synchronously-awaited CLI invocation with no
scheduler, no daemon, no autonomous trigger. The profile-staleness gap
(tied to "must be resolved before any scheduled/autonomous run") is
unaffected and correctly remains deferred — stated plainly here rather than
silently relying on that boundary still holding.

## Alternatives considered

- **A `--i-have-validated-promptfoo` flag.** Rejected: an unverified
  self-assertion, the exact category of signal this project refuses to
  trust everywhere else.
- **Look up the `Opportunity` by id against `InMemoryOpportunityRepository`.**
  Rejected: not persistent across processes, so a real terminal session
  (`discover` in one process, `apply` in another) could never actually use
  it — would look real but not work.
- **Build a real Greenhouse `ATSAdapter` in this slice.** Rejected: a real
  integration slice deserving its own design pass, not a rider on CLI
  wiring; explicitly asked and answered.
- **Re-derive `sys.argv` inside `main()` instead of accepting `argv`.**
  Rejected: would have left the pre-existing scaffolding test permanently
  broken under pytest, or required monkeypatching `sys.argv` in tests
  instead of the injection pattern already used throughout this project.

## Trade-offs

- **(+)** The first real, runnable command exists: a real profile and a
  real opportunity can be tailored, gated, rendered, and confirmed by an
  actual person in an actual terminal. ADR-0016's promptfoo requirement is
  now a structural check, not a policy a future run could silently skip.
  Every new guarantee in this slice (the promptfoo gate itself, its
  ordering before real client construction, and the `argv` fix) was
  verified by deliberate violation-injection, not merely asserted.
- **(−)** `apply` still cannot submit anything real — it is confirmation-only
  until a real `ATSAdapter` exists. Opportunity input is a manual file, not
  a discovery pipeline. No multi-tier selection exists yet (named, deferred
  since ADR-0024) — a confirmed application has no dispatch target even
  once a real adapter exists, for opportunities where `TieredApplicator`'s
  single adapter doesn't apply.

## Consequences

- `src/career_agent/llm/promptfoo_gate.py` (new):
  `verify_promptfoo_results`, `PromptfooNotValidatedError`.
- `src/career_agent/cli.py`: `apply` subcommand added (`run_apply_command`,
  `_apply_pipeline`, `_load_opportunity`); `main()` now takes `argv`.
- `promptfoo/README.md` must document the `-o
  <results_dir>/<prompt_version>.json` output convention
  `verify_promptfoo_results` depends on, so a real promptfoo run actually
  produces a file this command will find.
- The next real ATS integration slice must wire a real `Applicator` into
  `_apply_pipeline` (or a successor) once it exists — this ADR deliberately
  leaves that connection unbuilt.

## Future revisit criteria

Revisit if:

- A real `ATSAdapter` is built — `apply` should then actually submit on a
  confirmed "yes" rather than stopping and printing that nothing was sent.
- A `discover` command is built — it should produce the same
  `--opportunity-file` JSON shape `apply` already reads, or a persistent
  `OpportunityRepository` is built and `apply` gains an `--opportunity-id`
  lookup path alongside (not instead of) the file handoff.
- Real multi-tier selection is designed (ADR-0024's still-deferred item) —
  `apply` will need to choose an `Applicator` rather than assuming exactly
  one.
- `apply` gains any scheduled or autonomous invocation path — at that
  point the deferred profile-staleness gap must be resolved first, per its
  own stated trigger condition.
