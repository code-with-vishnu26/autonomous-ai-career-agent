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

``browser_applicator.py``'s identity-filling (Phase 8f, ADR-0027) now fills
real applicant identity read from ``Application.applicant`` (a required,
frozen ``BasicsSection`` snapshot populated once in
``ResumeTailoringPipeline``, the same "was this true when submitted"
discipline ``profile_version`` already applies to resume content) rather
than the hardcoded placeholder strings this class filled with before that
field existed.

``form_fillers.py`` (Phase 8g, ADR-0028) generalizes Tier 2's dispatch past
Greenhouse-only: which ATS's form to fill is resolved from
``resolve_ats_kind`` (the same pattern-match ADR-0019 reuses), dispatching
to a per-``ats_kind`` :class:`~career_agent.agents.apply.form_fillers.
FormFiller`. Only ``GreenhouseFormFiller`` is real -- Lever's and Ashby's
real field selectors could not be verified against a live posting from
this codebase (see that module's docstring for why), so
``LeverFormFiller``/``AshbyFormFiller`` are explicit stubs that raise
rather than guess. ``BrowserApplicator`` also now refuses, before ever
clicking submit, any *required* form field a ``FormFiller`` doesn't
declare knowing how to fill (:class:`~career_agent.agents.apply.
browser_applicator.UnsupportedFormFieldsError`) -- a platform-agnostic
check against the live page's real form elements, not a per-platform
guess-list. This deliberately does **not** attempt to answer custom
questions or EEOC/demographic fields in any way, including via LLM
drafting or "guess then confirm" -- that entire category of question is
named, deferred future work requiring its own dedicated design pass, not
folded into this dispatch mechanism (ADR-0028's Future revisit criteria).

A real, human dev-tools inspection of a live Lever posting (Phase 8h,
ADR-0029) -- the one verification path no automated tool in this codebase
or session could reach -- found ``FormFiller``'s own shape needed to
generalize further: real Lever identity fields have no ``id`` attribute at
all, only ``name``, and the posting used real hCaptcha markup neither the
old hardcoded ``#verification-challenge``/``#submit_app`` literals nor
``_unhandled_required_fields``'s ``#id``-only selector derivation could
ever have matched. ``FormFiller`` now declares
``challenge_selector``/``submit_selector`` per platform (read by
``BrowserApplicator`` instead of hardcoded values), and
``_unhandled_required_fields`` derives a field's selector from whichever
attribute it actually has. ``LeverFormFiller``/``AshbyFormFiller`` still
stay stubs -- the resume field's real interaction shape (plain text vs. a
JS-driven file-upload widget, with no resume-file artifact anywhere in
this project's domain model) is a separate, still-unconfirmed unknown that
real selectors alone don't resolve.

A real, human dev-tools inspection of a live Greenhouse posting (Phase 8i,
ADR-0030) -- applied to the one platform this project had treated as its
fully proven baseline -- confirmed ``resume_text`` is a real, visible
"Enter manually" form option (not merely documented in Greenhouse's API),
though the exact toggle interaction and revealed field's real selector
remain unconfirmed. More consequentially, the same **ordinary** posting
required Education, three legal work-authorization questions, a full
Voluntary Self-Identification section, and Veteran Status -- none of which
``GreenhouseFormFiller`` fills. ``_unhandled_required_fields`` correctly
refuses on all of them, exactly as designed. **This corrects the record,
not the code: "Tier 2 works for Greenhouse" has only ever meant "correctly
refuses most real postings, completing only the minority with minimal
custom fields," not "completes most real Greenhouse applications."** The
deferred custom-questions/EEOC-answering design (named since Phase 8g) is
therefore not a generalization nice-to-have -- it is the actual gate on
this project's practical usefulness on the one platform it already
supports.

Remaining future work: real per-question-type answering for custom/EEOC
questions -- now understood as load-bearing for practical completion, not
just thorough (its own dedicated ADR, not this one); confirming the exact
Greenhouse resume-field interaction sequence; resolving the resume-field
interaction shape and confirming Lever's selectors generalize across more
than one company before ``LeverFormFiller`` can move past a stub; Ashby's
DOM remains fully uninspectable by every tool tried so far (a client-side
React SPA); multi-tier selection; and the real, OAuth-backed Gmail client.
A real, runnable `career-agent apply` command exists as of Phase 8e
(ADR-0026).
"""
