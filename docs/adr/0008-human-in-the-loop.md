# ADR-0008: Human-in-the-loop application

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0000](0000-project-philosophy.md) (Golden Rule #6),
  [ADR-0010](0010-hybrid-application-strategy.md)

## Context

Submitting applications touches systems that are deliberately gated against
automation: CAPTCHAs, email/phone verification, anti-bot checks, and login flows
(including Google OAuth). The project's philosophy ([ADR-0000](0000-project-philosophy.md))
forbids bypassing these, and the user must remain in control of what is sent in
their name from their accounts.

## Problem

How does the agent automate the tedious parts of applying while never bypassing
protections, never acting beyond the user's authority, and keeping the user in
control of final submission?

## Decision

Applying is **supervised and human-in-the-loop** by design.

- **Pause, never bypass.** On any CAPTCHA, verification, or anti-bot challenge, the
  agent **pauses and hands control to the human** to clear it, then resumes. It
  never solves, circumvents, or outsources these (Golden Rule #6).
- **Reuse a human-established session.** The browser tier reuses a session the user
  established by **manual login**; the agent **never automates Google OAuth** or
  other logins the provider intends a human to perform.
- **Throttled and rate-limited.** Submissions are paced to respect platforms and to
  reflect the quality-over-volume objective — this is not a mass-apply tool.
- **User-defined controls & confirmation.** The user configures autonomy: which
  steps auto-proceed and which require explicit confirmation before submission. The
  truthfulness gate ([ADR-0003](0003-truthfulness-gate.md)) must pass before any
  submission regardless of autonomy level.
- **Resumable pauses.** Because the Planner is built on a resumable state machine
  ([ADR-0007](0007-planner-agent.md)), a pause for human action is a first-class
  state, not a crash — the workflow continues cleanly once the human acts.

## Alternatives considered

- **Fully autonomous submission.** Maximizes throughput, but requires bypassing
  protections and removes user control — violates Golden Rules #6 and #7. Rejected
  outright.
- **CAPTCHA-solving services.** Technically possible, but bypasses an anti-automation
  control by proxy and risks ToS violations. Rejected.
- **Fully manual (agent only drafts).** Safest, but discards most of the automation
  value. Rejected as the default; the user *may* configure near-manual autonomy if
  they wish.

## Trade-offs

- **(+)** Ethical and ToS-respecting; user stays in control; aligns with
  quality-over-volume; pauses are clean and resumable.
- **(−)** The user must be available to clear challenges, so throughput is bounded by
  human attention (acceptable and intentional for a single user); supervised flows
  are more complex than fire-and-forget.

## Consequences

- The tiered applicator ([ADR-0010](0010-hybrid-application-strategy.md)) embeds
  pause/resume points at each tier.
- Notifications (a cross-cutting sink) alert the user when their action is needed.
- Autonomy configuration becomes part of user settings (later phase).

## Future revisit criteria

Revisit if:

- A platform offers a sanctioned automation/API path that removes the need for
  manual challenge-clearing.
- The legal/ToS landscape changes the acceptable level of automation.
- Users consistently request finer-grained autonomy controls than the model
  provides.
