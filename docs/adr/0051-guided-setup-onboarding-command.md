# ADR-0051: Guided `setup` onboarding command (Phase 25)

- **Status:** Accepted
- **Date:** 2026-07-06
- **References:** [ADR-0017](0017-json-resume-master-profile.md) (the JSON
  Resume profile format the scaffold targets), [ADR-0037](0037-persistence-discover-and-first-profile-writer.md)
  (the `capture-legal-status` profile writer this complements),
  [ADR-0043](0043-zero-cost-truthfulness-gate-provider.md) (the Groq
  free-tier verifier the readiness report checks for)

## Context

Phase 25 was a cross-repository competitive audit against
`MadsLorentzen/ai-job-search` (MIT-licensed, pinned at commit `79b1537`),
a Claude-Code-driven markdown/skills workspace. The audit's decisive
finding was not a missing algorithm or a safety gap -- our deterministic
architecture (truthfulness gate, Promptfoo validation, Decide layer with
the proven ADR-0047 dominance invariant, ADR-0048 idempotency, ADR-0049
journal, ADR-0050 execution boundary) is materially stronger on rigor and
safety than the reference, whose fit-scoring and truthfulness protection
are prompt-only and whose "apply" flow is an unenforced LLM reviewer loop.

The reference's genuine advantage is **time-to-first-useful-result**. Its
`/setup` command offers three onboarding paths (read a `documents/`
folder, import a single CV, or an interactive interview), extracts a
structured profile, labels every inferred fact for review, and confirms
before writing. Ours had **no onboarding command at all**: a new user had
to reverse-engineer the JSON Resume schema (including this project's
required `id` extension on every entry, ADR-0017) and hand-author a
profile file, with no scaffold, no example, and no way to check whether
their keys/validation were configured. Verified by inspection: the CLI
exposed `apply/discover/auto/capture-legal-status/outcome/report/export/
verify-promptfoo/diagnose-promptfoo-drift` -- nothing for getting started.

The multi-objective prioritization (transparent 0-5 ordinal vectors over
user-value / gap-severity / safety / cost / regression-risk / alignment,
Pareto + scalar tie-break + weight sensitivity) put "guided setup" on the
Pareto frontier and stable as the top pick under reasonable weight
perturbations: highest verified gap severity, high user value, near-zero
cost, near-zero regression risk (a new additive command), and full
architectural alignment. Interview-prep and a drafter/reviewer loop ranked
lower (both LLM-dependent, harder to test zero-cost, and the reviewer loop
carries a real truthfulness-interaction question -- see "Rejected").

## Decision

Add a deterministic, fully-offline `career-agent setup` command
(`run_setup_command` in the CLI composition root; scaffold generation in
`storage/profile.py`) that does exactly three things and no more:

1. **Scaffolds a schema-correct starter profile** (`write_profile_scaffold`
   / `example_profile_dict`) at `--profile` (default `profile.json`) **if
   and only if no file exists there**. The scaffold is a valid JSON Resume
   document with this project's required `id` extension and obvious
   placeholder values ("Your Name", "you@example.com"). A round-trip test
   pins it to `load_master_profile`, so it can never drift into an
   unloadable shape.
2. **Prints an offline readiness report**: does the profile load; is a
   provider key present (Groq preferred, Anthropic fallback -- **presence
   only, the key value is never printed**, verified by test); is a
   Promptfoo results artifact present; what data paths are configured.
3. **Names the single next command**, chosen deterministically from that
   state (edit the profile → set a key → run Promptfoo → `discover`).

### Safety properties

- **Never overwrites an existing profile.** `write_profile_scaffold`
  returns `False` and touches nothing if the target exists -- a real
  profile is never destroyed (tested).
- **The scaffold is not evidence.** It is obvious placeholder text the
  user edits into real facts; nothing in it is ever treated as verified.
  This honors the audit's onboarding safety rule ("LLM extraction must
  never silently become verified evidence") trivially, by not doing LLM
  extraction at all in this slice.
- **Zero LLM, zero network, no secret printed.** The readiness checks read
  `Settings` (env), glob a local directory, and call `load_master_profile`
  -- all offline. `setup` always returns 0; it is advisory, never a gate,
  and cannot fail any other flow.
- **No safety mechanism touched.** Truthfulness, Promptfoo validation,
  confirmation, ADR-0048 idempotency, ADR-0049 journaling, and ADR-0050's
  execution boundary are all unchanged; `setup` reaches none of them.

## Alternatives considered / rejected (this phase)

- **LLM-based CV extraction (the reference's Path A/B).** Deferred: it is
  LLM-dependent (not zero-cost-testable) and larger than one reviewable
  PR. The deterministic scaffold captures most of the friction reduction
  (a known-valid starting file) without an LLM. If added later, extracted
  facts must be written as an editable draft the user confirms, never as
  verified evidence -- explicitly noted for that future phase.
- **A drafter/reviewer revision loop (the reference's `/apply`).**
  Deferred and flagged: the reference's reviewer can introduce new
  claims/keywords and its only guard is a prompt instruction ("do not
  fabricate"), with no deterministic re-gate. Adopting a reviewer loop
  here would be safe **only** if every revision re-passes the truthfulness
  gate and ATS gate (Draft → Review → Revision → TruthfulnessGate →
  ATSGate → Accept/Reject), which is a genuine design question worth its
  own phase, not folded in here.
- **Interview-prep pack.** Real gap (we have none; the reference has an
  LLM-filled STAR-example skill), but LLM-dependent and lower priority
  than onboarding; classified ADOPT_LATER.

## Consequences

- `storage/profile.py`: `example_profile_dict()` + `write_profile_scaffold()`.
- `cli.py`: `run_setup_command(...)`, a `setup` subparser, and its
  dispatch. Additive -- no existing command changed.
- `tests/test_setup_command.py`: scaffold round-trips through the real
  loader; never overwrites an existing profile; readiness/next-action are
  correct across states; the key value is never printed; an unloadable
  profile is reported without crashing; `main(["setup"])` dispatches with
  the documented default path.
- Zero cost, zero network, zero new dependency; no live LLM/browser/email
  calls. No production behavior of `apply`/`auto`/`discover` changed.
