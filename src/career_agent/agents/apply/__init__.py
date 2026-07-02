"""Apply Agent (Phase 7).

Submits applications through a tiered applicator: direct ATS API -> driven browser
(Playwright + Browser-Use) -> email-to-apply via Gmail. Throttled and supervised:
pauses for the human to clear CAPTCHA/verification, reuses a manually established
session, and never automates Google OAuth.

``applicator.py`` (Phase 7a/7b1, ADR-0018/ADR-0019) is Tier 1: the
submission safety machinery (structural approval via
:class:`~career_agent.domain.models.SubmittableApplication`,
confirmation-token binding) plus ATS-kind resolution from an opportunity's
``source_url`` against a set of registered Tier 1 ATS adapters
(:class:`~career_agent.core.interfaces.ATSAdapter`). By design, tier
fallback is never an automatic retry under one confirmation; each tier
attempt requires its own (ADR-0019).

``browser_applicator.py`` (Phase 7b3, ADR-0020) is Tier 2: drives a real
browser through Greenhouse's public apply form only, this slice. Adds a
second structural guarantee alongside confirmation-token binding: a
mid-submission challenge (CAPTCHA/verification/login) pauses the live
session and can only be resumed by a token-bound
:class:`~career_agent.domain.models.PauseAcknowledgment` that ``resume()``
re-verifies against the actual page state, not just trusts. Persisted
sessions are encrypted at rest with an OS-keychain-held key
(:mod:`~career_agent.integrations.browser_session`), fail-closed if the
keychain is unavailable.

``email_applicator.py`` (Phase 7b4, ADR-0021) is Tier 3: creates a draft
email via an injected :class:`~career_agent.core.interfaces.EmailDraftSink`
-- which has **no send method at all**, a deliberate interface-level scope
restraint, not an external fact. ``submit()`` therefore never returns
``ApplicationSubmitted``, only ``HumanActionRequired`` -- claiming a send
that didn't happen would be the truthfulness gap ADR-0003 exists to
prevent. The real, OAuth-backed ``GmailDraftSink`` is not built yet
(deliberately -- an OAuth token needs the same dedicated review
ADR-0020 gave session encryption).

Remaining Tier 1 adapters, generalizing Tier 2 beyond Greenhouse's form
shape, and the real Gmail client are still future work.
"""
