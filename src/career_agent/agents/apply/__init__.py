"""Apply Agent (Phase 7).

Submits applications through a tiered applicator: direct ATS API -> driven browser
(Playwright + Browser-Use) -> email-to-apply via Gmail. Throttled and supervised:
pauses for the human to clear CAPTCHA/verification, reuses a manually established
session, and never automates Google OAuth.

``applicator.py`` (Phase 7a, ADR-0018) is the first concrete piece: the
submission safety machinery (structural approval via
:class:`~career_agent.domain.models.SubmittableApplication`,
confirmation-token binding) proven correct against exactly one injected
:class:`~career_agent.core.interfaces.ATSAdapter`. Multi-tier fallback
(browser, email) and company/ATS-kind resolution are follow-up sub-slices,
not yet built.
"""
