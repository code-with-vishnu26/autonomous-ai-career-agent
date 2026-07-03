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

``pipeline.py`` (Phase 8c, ADR-0024) composes any
:class:`~career_agent.core.interfaces.Applicator` with any real or fake
confirmation source into ``prepare() -> confirm() -> submit()``, or a clean,
non-error abort on a declined confirmation --
:func:`~career_agent.cli.confirm_submission` is the first real one,
deliberately built now rather than deferred (unlike
``AnthropicClaimVerifier``/the real ``GmailDraftSink``, a local stdin/stdout
prompt is fully testable in this sandbox, so that deferral precedent
doesn't transfer). Single-tier only this slice -- multi-tier selection
across the three ``Applicator`` implementations above remains real,
confirmed, unbuilt work (ADR-0010's "tier selection is internal" describes
a component that was never actually built).

Real Tier 1 (``ATSAdapter``) submission for arbitrary companies is
**confirmed dead, not merely deferred** (Phase 8f, ADR-0027): Greenhouse's,
Lever's, and Ashby's submit-side endpoints each require an employer-issued
API credential a generic applicant tool has no path to obtaining, verified
against each platform's own current API docs. Tier 2 (``BrowserApplicator``)
is therefore the only tier that can carry real submission weight for this
project's use case -- it drives the same public apply form a human uses,
requiring no company cooperation.

``browser_applicator.py``'s ``_fill_form`` (Phase 8f, ADR-0027) now fills
real applicant identity read from ``Application.applicant`` (a required,
frozen ``BasicsSection`` snapshot populated once in
``ResumeTailoringPipeline``, the same "was this true when submitted"
discipline ``profile_version`` already applies to resume content) rather
than the hardcoded placeholder strings this class filled with before that
field existed. Its name-splitting heuristic is a documented,
known-imprecise stopgap, not an assumed-correct split.

Remaining future work: generalizing Tier 2 beyond Greenhouse's one form
shape (which reopens the per-posting custom-questions/EEOC problem that
killed Tier 1, now as its own truthfulness-adjacent design question);
multi-tier selection; and the real, OAuth-backed Gmail client. A real,
runnable `career-agent apply` command exists as of Phase 8e (ADR-0026).
"""
