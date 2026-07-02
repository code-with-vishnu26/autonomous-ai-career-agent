"""Apply Agent (Phase 7).

Submits applications through a tiered applicator: direct ATS API -> driven browser
(Playwright + Browser-Use) -> email-to-apply via Gmail. Throttled and supervised:
pauses for the human to clear CAPTCHA/verification, reuses a manually established
session, and never automates Google OAuth.

``applicator.py`` (Phase 7a/7b1, ADR-0018/ADR-0019) is the first concrete
piece: the submission safety machinery (structural approval via
:class:`~career_agent.domain.models.SubmittableApplication`,
confirmation-token binding) plus ATS-kind resolution from an opportunity's
``source_url`` against a set of registered Tier 1 ATS adapters
(:class:`~career_agent.core.interfaces.ATSAdapter`). Multi-tier fallback
(browser, email) is a follow-up sub-slice -- and, by design, will never be
an automatic retry under one confirmation; each tier attempt requires its
own (ADR-0019).
"""
