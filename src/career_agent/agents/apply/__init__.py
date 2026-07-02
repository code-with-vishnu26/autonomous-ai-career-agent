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

Tier 3 (email, via Gmail) and generalizing Tier 2 beyond Greenhouse's form
shape are still future work.
"""
