# ADR-0020: Browser-tier session encryption and the pause/resume token

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0008](0008-human-in-the-loop.md) (session reuse from
  manual login, pause-never-bypass), [ADR-0010](0010-hybrid-application-strategy.md)
  (Tier 2, the browser applicator), [ADR-0018](0018-submission-safety.md)
  (`SubmittableApplication`, `prepare`/`submit`, `HumanConfirmation` token
  binding, all extended here), [ADR-0019](0019-ats-kind-resolution-and-tier-fallback.md)
  (Greenhouse-first precedent, no cross-tier auto-retry)

## Context

Phase 7a/7b1 built Tier 1 (direct ATS API) submission with structural
approval and confirmation-token binding. Tier 2 (browser) is a different
category of risk: it holds a **live, authenticated browser session** tied to
a real personal account, and it can hit a CAPTCHA or verification wall
mid-submission that only a human can clear. Neither problem existed for
Tier 1. Before any adapter code, three questions needed real answers: where
a persisted session lives and whether it's protected at rest, whether the
human-clears-the-challenge pause is structural or a policy note, and how
wide a slice of real-world form shapes this phase should target.

## Problem

How does `BrowserApplicator` persist a reusable, authenticated session
without creating the first plaintext-secret-on-disk problem in this project,
and how does a mid-submission challenge pause a live browser session with
the same "impossible to advance otherwise" guarantee `HumanConfirmation`
already gives submission itself?

## Decision

### Session storage: encrypted at rest, key in the OS keychain, fail-closed

A Playwright `storage_state` (cookies + localStorage) is not like an API key
— it doesn't just grant read access to a value, it lets something **act as
the user** on a real site. That is a categorically higher-stakes secret than
anything `core/config.py`'s `.env` pattern protects, so it does not rest on
an assumption about the host's disk configuration (full-disk encryption may
or may not be in place, and this project has no way to verify it) — the same
"never trust an unverified signal" discipline already applied everywhere
else (a URL pattern is confirmed by re-parsing, not trusted on shape; a
verifier's confidence is thresholded, not trusted as a bare boolean).

`integrations/browser_session.py`'s `EncryptedSessionStore` encrypts the
serialized session (Fernet, authenticated encryption) with a key obtained
through a `KeyProvider` port. The real implementation,
`KeyringKeyProvider`, stores the key in the OS credential store via the
`keyring` package — the key and the ciphertext it protects are never
together in the same file. **Fail-closed, not fail-open:** if the keychain
backend is unavailable (a real, expected case in headless/container
environments, including this sandbox), `save`/`load` raise
`SessionEncryptionUnavailableError` rather than falling back to writing the
session unencrypted. The cost is a forced manual re-login on the next run;
that is the correct trade against a session file that, if it ever leaves the
machine (backup, sync tool, a compromised process), is immediately usable by
whoever has it. Tests inject a `FakeKeyProvider` (including one that
simulates unavailability) — the real `keyring` backend is untestable live in
this sandbox, disclosed the same as every other real external-system client
in this project.

### Pause/resume: `HumanActionRequired` + a token-bound `PauseAcknowledgment`, not a policy note

A mid-submission challenge (CAPTCHA, verification, login wall) must produce
the same kind of guarantee `HumanConfirmation` gives ordinary submission:
structurally impossible to advance without a specific, matching human act —
not "the orchestration code is expected to wait." `BrowserApplicator.submit`
does not poll, wait, or retry when a challenge appears; it returns
`HumanActionRequired` (an event type defined in Phase 2's event catalog,
unused until now — reused rather than a new mechanism invented, the same
discipline as reusing `HeldCandidateSink` for search results instead of a
second uncertainty channel) and holds the live browser page open, untouched.

`resume(pause_token, ack: PauseAcknowledgment)` is the only way to continue.
`PauseAcknowledgment` mirrors `HumanConfirmation`'s shape deliberately:
`pause_token` must name the exact pause being cleared. Critically,
`resume()` does not trust the acknowledgment alone — it **re-checks the
challenge is actually gone on the live page** before touching it again,
raising `ChallengeStillPresentError` without re-clicking submit if it's
still visible. This is a harder guarantee than `HumanConfirmation`'s: that
token binding protects a *type that can't be constructed*; this protects
*live, mutable browser state that must stay paused* until independently
verified clear, not just acknowledged clear.

### Scope: Greenhouse's public apply form only, this slice

Same reasoning as Phase 4a choosing Greenhouse first to prove the
`OpportunitySource` contract, and ADR-0019 choosing it again for the ATS-kind
resolution proof: this slice proves the session/pause machinery correct
against one well-understood, structurally uniform form shape, not arbitrary
company career pages. Generalizing to other sites is real, separate future
work — solving browser automation, session encryption, and pause/resume
*and* arbitrary form detection in one slice would make it impossible to tell
which part of a failure came from which problem.

### Testing: real Playwright against a local fixture, not Python-level fakes

`tests/fixtures/greenhouse/apply_form.html` is a local, offline HTML page
(loaded via `file://`, no network) shaped like a Greenhouse-style apply form,
with a `?challenge=1` query flag that makes it show a verification panel
after the first submit click — mimicking a real mid-flow challenge. Tests
drive a real, locally-installed Chromium against this fixture (this sandbox
ships one; a version-mismatch with the currently-installed Playwright means
tests locate it explicitly via `chromium_executable_path` rather than
Playwright's default resolution — production use passes no override). This
is a materially stronger proof than a Python-level `FakeATSAdapter`-style
double would have been: the pause/resume tests assert against the real
page's own DOM state (`page.is_visible("#verification-challenge")`,
`page.is_visible("#application-success")`), not a fake's recorded call log.
The load-bearing test asserts the fixture's own success marker **never
appears** when `resume()` is called with the challenge still visible — the
real click action genuinely never fires, verified independently of whether
an exception was raised, the browser-tier analogue of asserting
`adapter.calls == []` in ADR-0018.

## Alternatives considered

- **Rely on host full-disk encryption, gitignore the session directory.**
  Rejected: an unverifiable assumption about an environment this project
  doesn't control, the same category of risk this project has refused to
  build on everywhere else.
- **Silently fall back to unencrypted storage if the keychain is
  unavailable.** Rejected: would make the encryption guarantee
  environment-dependent and undetectable — exactly the "probabilistic
  discipline applied to a should-be-structural guarantee" failure mode
  rejected in ADR-0018's `SubmittableApplication` design.
- **A boolean/timeout-based auto-continue for the pause.** Rejected: exactly
  the failure mode `HumanConfirmation` was built to prevent for ordinary
  submission; a live session is not a lower-stakes case than an unconfirmed
  API call, if anything the reverse.
- **Trusting the acknowledgment alone in `resume()`, without re-checking the
  live page.** Rejected: an acknowledgment could be stale (issued before the
  challenge was actually cleared, or for a different pause entirely) —
  re-verifying against the page itself is what makes this a real guarantee
  rather than a documented expectation.
- **Generalizing to arbitrary career pages in this slice.** Rejected as
  premature scope, same reasoning as Greenhouse-first in Phase 4a and
  ADR-0019.

## Trade-offs

- **(+)** A live session cannot be read without the OS keychain's
  cooperation; a paused submission cannot advance without both a matching
  token and independently-verified confirmation that the blocking condition
  is actually gone; the pause/resume guarantee is proven against real
  browser behavior, not simulated.
- **(−)** New dependencies (`cryptography`, `keyring`) and a new failure
  mode (keychain unavailable) that forces manual re-login more often in
  constrained environments; this slice only covers one real form shape, not
  general browser-tier coverage.

## Consequences

- `integrations/browser_session.py` (new): `KeyProvider` Protocol,
  `KeyringKeyProvider`, `EncryptedSessionStore`,
  `SessionEncryptionUnavailableError`, `SessionCorruptedError`.
- `domain/models.py`: `PauseAcknowledgment` added, mirroring
  `HumanConfirmation`.
- `agents/apply/browser_applicator.py` (new): `BrowserApplicator`
  (`prepare`/`submit`/`resume`), `UnknownPauseTokenError`,
  `ChallengeStillPresentError`.
- `tests/fixtures/greenhouse/apply_form.html` (new): the local, offline form
  fixture real Playwright is driven against.
- New dependencies declared: `cryptography>=42.0`, `keyring>=25.0`.
- Generalizing beyond Greenhouse's form shape, and wiring `BrowserApplicator`
  into any orchestration layer (a future Apply Agent), remain future work.

## Future revisit criteria

Revisit if:

- A second real form shape (Lever, Ashby, or an arbitrary company page) is
  targeted — the field-selector logic in `_fill_form`/the challenge-detection
  selectors will need to generalize past hardcoded Greenhouse-fixture ids.
- Keychain unavailability proves common enough in real deployments that a
  documented, explicit user opt-in to a weaker storage mode is worth
  designing (never a silent default).
- `browser-use` (declared as a dependency, unused so far) is evaluated
  against raw Playwright for the generalization work.
- A real orchestration layer (Apply Agent) is built and needs to call
  `resume()` from outside the same process/session that called `submit()` —
  today's in-memory `_paused` dict does not survive a process restart.
