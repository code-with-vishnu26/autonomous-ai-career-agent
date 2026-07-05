# ADR-0041: The two pre-scheduling gates close; scheduling is a bounded, submission-free pass

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0018](0018-submission-safety.md) (recorded the
  profile-staleness gap), [ADR-0021](0021-email-tier-draft-only.md)
  (recorded the send-confirmation gap; the no-send interface restraint
  reused here), [ADR-0008](0008-human-in-the-loop.md) (the line
  scheduling must never cross)

## Decision

**Gate (a) — profile-staleness re-verification (`StaleProfileError`).**
`SubmissionPipeline` accepts `current_profile_version`; a mismatch with
the application's frozen `profile_version` refuses **before `prepare()`
ever runs** — a stale application never even produces a preview a human
could mistakenly confirm (proven by the `applicator.calls == []` shape;
injection-verified: disabling the check was caught). The fix is named in
the error: re-run tailoring, which re-gates everything. Omitting the
parameter preserves existing behavior (backward compatible, tested).

**Gate (b) — email send-confirmation (`integrations/sent_mail.py`).**
`SentMailChecker` — a read-only "does this message exist in SENT?" port
with **no send capability anywhere on it** (EmailDraftSink's restraint,
re-applied; tested against the port surface). `confirm_email_sent`
advances only on a *positive observation*; a checker failure raises the
typed `SentCheckUnavailableError` — "we couldn't look" is never coerced
into a yes or a no. The real OAuth Gmail checker stays deliberately
unbuilt here (sandbox-untestable; a Google OAuth token needs the same
user-present review ADR-0020 gave session encryption) — the user
validates it live; the decision logic it plugs into is done and tested.

**Scheduling: `career-agent auto` — one bounded pass, cron-invokable.**
discover → rank (ADR-0038) → tailor+gate top N (both gates in full) →
record → notify "waiting for YOUR confirmation." **Structurally cannot
confirm or submit**: no input function in its signature, no
`HumanConfirmation`, no `Applicator`, no `SubmissionPipeline` anywhere in
its code — asserted by the 1d-shape structural test over
`__code__.co_names`, not by convention. Recurrence itself belongs to the
user's own scheduler (cron) invoking this command — this project runs a
pass when asked; it does not run itself. Confirmation and submission
remain human-gated forever (ADR-0008), stated here as the permanent
boundary, not a current limitation.

**Still-deferred 7-series items, restated:** multi-tier selection across
the three Applicators (real design work, unbuilt), the real OAuth
`GmailDraftSink` and `SentMailChecker` implementations (user-validated,
live-only). Phase 18 (Ashby) remains blocked on the user's dev-tools DOM
inspection — nothing is built on assumption.

## Future revisit criteria

- The user's live Gmail validation lands → wire the real checker into an
  email-draft advance flow.
- Multi-tier selection is designed → `auto` may then prepare per-tier;
  the no-submit boundary is unaffected.
