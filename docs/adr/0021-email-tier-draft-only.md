# ADR-0021: Email tier is draft-only, never claims submission

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0003](0003-truthfulness-gate.md) (the truthfulness
  principle this ADR extends to the system's own claims about its actions),
  [ADR-0008](0008-human-in-the-loop.md) (never automate Google OAuth),
  [ADR-0010](0010-hybrid-application-strategy.md) (Tier 3), [ADR-0018](0018-submission-safety.md)
  (`prepare`/`submit`, `HumanConfirmation` token binding, extended here),
  [ADR-0020](0020-browser-tier-session-and-pause.md) (the encrypted-secret
  precedent an OAuth token would fall under, deferred here)

## Context

Tier 3 (email-to-apply) needed a mechanism for sending an application by
email and a decision about how confirmation applies to it. During design, a
factual check corrected the premise the pre-brief started from: the Gmail
tool surface available in the *development* environment (this Claude Code
session) exposes only draft creation, no send — but that is a fact about
this session's connector configuration, not about the Gmail API in general,
and not something the shipped `career_agent` application (which runs
standalone on a user's machine, with its own OAuth-configured client) would
inherit "for free." The real guarantee had to come from how this project
scopes its own port, not from an external fact.

## Problem

How does Tier 3 send an application by email without (a) building a second,
undesigned credentials-security problem (an OAuth token, in the same risk
category ADR-0020 just solved for browser sessions), and (b) letting the
system's own application-status claims become untrue, the same failure mode
ADR-0003 exists to prevent for resume content?

## Decision

### `EmailDraftSink`: a port with no `send` method, by design, not by external fact

`core/interfaces.py`'s `EmailDraftSink` Protocol exposes exactly one method,
`create_draft`. There is no `send` on the interface at all. This is a
deliberate scope restraint this project holds itself to: the real Gmail API
can send mail, and a future implementation of this Protocol could
technically call that endpoint if the interface were widened to allow it —
but doing so is a visible, reviewable interface change, not something that
can happen by accident inside `EmailApplicator`. Pinned by a canary test
(`test_email_draft_sink_protocol_has_no_send_method`, same shape as
ADR-0019's `Applicator` canary), verified to bite the same way every other
guardrail in this project has been: a `send` method was injected, the test
failed, it was reverted.

### `submit()` never returns `ApplicationSubmitted`

`EmailApplicator.submit()` creates a draft (gated by the same
confirmation-token binding as `TieredApplicator`/`BrowserApplicator`:
unknown, mismatched, or replayed tokens are refused before
`EmailDraftSink.create_draft` is ever called, proven the same way — the
sink's call log stays empty) and always returns
`HumanActionRequired(reason="confirmation")` — the `Literal` value defined
in Phase 2's event catalog and, until this slice, unused. Claiming
`ApplicationSubmitted` after only creating a draft would be false: the
truthfulness gap would move from resume content (what ADR-0003 already
guards) to the system's own claims about what it did, arguably worse, since
it would be the system misrepresenting itself rather than the user's
history.

### `Application.status="paused_for_human"` means two structurally different things

Documented directly on `Application` (`domain/models.py`), not left implicit:
a browser-tier pause (ADR-0020) is *temporary* — the live session is held
open and `BrowserApplicator.resume()` can advance it once a human clears the
blocking challenge. An email-tier pause is *permanent* from this system's
perspective — a draft was created and there is no `resume()` for this tier
at all, because sending is a capability `EmailApplicator` never has access
to. A future dashboard/notification surfacing `paused_for_human`
applications as one undifferentiated list must not imply a uniform "resume"
action exists for both.

### Recipient-address resolution and send-confirmation are named, out-of-scope gaps

Two real gaps, not solved here:

- **Recipient address.** `Opportunity` has no modeled "apply by email"
  address; `EmailApplicator.prepare()` reuses `source_url` as the target,
  which is a placeholder, not real address discovery. Future work.
- **Confirming a drafted email was actually sent.** Nothing today lets the
  system learn a draft moved from `paused_for_human` to genuinely sent (e.g.
  polling `SENT` and matching a message back to a specific draft). Low risk
  for a one-off manual session (create the draft, go send it in the same
  sitting); real risk once applications run unattended over days, where an
  unconfirmed `paused_for_human` pile becomes impossible to distinguish
  "stale and abandoned" from "genuinely pending." **Tied to the same trigger
  as the profile-staleness gap (ADR-0018): must close before any
  scheduled/autonomous apply run is built**, not left as untethered future
  work.

### The real `GmailDraftSink` (OAuth-backed) is not built this slice

Building the actual Gmail API client means handling an OAuth refresh token —
another credentials-adjacent secret in the same risk category ADR-0020 just
designed encryption for. Building it now, inside this slice, would be
quietly re-litigating that design without the dedicated review it deserves.
This slice ships `EmailApplicator` fully tested against `FakeEmailDraftSink`
only; the real, OAuth-backed `GmailDraftSink` is explicit follow-up work,
named rather than silently assumed to arrive for free alongside the
Protocol.

## Alternatives considered

- **Raw SMTP with a user-managed app password.** Rejected: introduces a
  second credentials-adjacent secret this project would have to protect
  (same category as the browser session) for no benefit over an existing
  API path, and doesn't benefit from OAuth's revocability.
- **`submit()` returning `ApplicationSubmitted` once a draft exists.**
  Rejected outright: false by construction, the system misrepresenting its
  own actions.
- **Giving `EmailDraftSink` a `send` method now, unused, "for completeness."**
  Rejected: an unused capability sitting on the interface is exactly the
  kind of thing that gets called accidentally or under pressure later,
  without the deliberate, visible decision this ADR requires of that step.
- **Building the real OAuth-backed `GmailDraftSink` in this slice.**
  Rejected as scope creep: OAuth token handling deserves the same dedicated
  design review ADR-0020 gave session encryption, not a rider on this ADR.

## Trade-offs

- **(+)** No new credentials-security surface this slice; the system's
  status claims stay honest; the interface itself, not just documentation,
  prevents an accidental send capability from appearing.
- **(−)** Tier 3 cannot fully automate an email application end-to-end — the
  human must still open their email client and click send themselves, every
  time. Recipient-address resolution and send-confirmation remain open gaps
  with no implementation yet, only a named trigger for when they must close.

## Consequences

- `core/interfaces.py`: `EmailDraftSink` added (additive).
- `agents/apply/email_applicator.py` (new): `EmailApplicator`.
- `domain/models.py`: `Application`'s docstring now distinguishes the two
  meanings of `paused_for_human`.
- `tests/_fakes.py`: `FakeEmailDraftSink` added.
- The real `GmailDraftSink` (OAuth-backed) and recipient-address resolution
  remain unbuilt; any future scheduled/autonomous apply-run phase is blocked
  on the send-confirmation gap closing first (shared trigger with ADR-0018's
  profile-staleness gap).

## Future revisit criteria

Revisit if:

- The real, OAuth-backed `GmailDraftSink` is built — its own credential
  storage should be reviewed against ADR-0020's encryption precedent, not
  assumed exempt.
- Recipient-address resolution for email applications is designed (a real
  field on `Opportunity`, or a discovery mechanism).
- Send-confirmation (polling `SENT`, matching back to a draft) is designed —
  required before any scheduled/autonomous apply run per the shared trigger
  above.
- A dashboard/notification phase needs to actually distinguish the two
  `paused_for_human` meanings in the UI, not just in code documentation —
  at that point a second status literal may be warranted.
