"""Tier 2 (browser) Applicator (ADR-0020, generalized in ADR-0028/ADR-0032).

Same confirmation-token discipline as :class:`~career_agent.agents.apply.
applicator.TieredApplicator` (ADR-0018) for ``prepare``/``submit``, plus a
second, analogous token for the one thing Tier 1 never has to handle: a
mid-submission pause. There are two distinct pause reasons, sequential by
construction, not by convention (ADR-0032):

**Phase A (pre-click, ``reason="fields_need_human_input"``).** After known
identity/resume fields are filled, every remaining required field is
classified via :mod:`~career_agent.agents.apply.question_answerer`. A
Category 2 (factual) field with an already-captured
:class:`~career_agent.domain.models.LegalStatusSection` fact is filled
automatically -- same tier as an ordinary known field, no pause. Everything
else unresolved (EEOC, subjective, a missing legal-status fact, or simply
any field this slice doesn't attempt to auto-resolve) is batched into a
**single** pause naming every unresolved selector. The human fills those
fields **directly on the live, visible page** -- ``resume()`` never takes a
typed answer payload and writes it into the DOM itself. This is deliberate,
not an implementation shortcut: an EEOC response this way never becomes a
Python value this process holds at any point, which is a categorically
stronger guarantee than "received it and used it correctly" -- there is
nothing here that could ever leak, log, or mis-route, because nothing is
ever held. ``resume()`` re-verifies every manifested field is actually
non-empty on the live page before proceeding -- never trusts the
acknowledgment alone (:class:`RequiredFieldsStillUnresolvedError`).

**Phase B (post-click, ``reason="challenge"``).** Unchanged from ADR-0020:
click, check for a CAPTCHA/verification wall, pause if present.
``resume()`` re-checks the challenge is actually gone before ever touching
the page again (:class:`ChallengeStillPresentError`).

No pause carries data the caller supplies back through ``resume()`` other
than the token match itself -- ``PauseAcknowledgment``'s shape (ADR-0020)
is reused unchanged for both phases, not given a second, richer shape.
Phase A cannot begin until Phase B is unreachable, and Phase B cannot begin
until Phase A's own resume has already re-verified and completed -- there
is no code path where a later pause skips an earlier one's check.

``BrowserApplicator`` has **zero dependency on ``MasterProfile`` storage**,
by deliberate structural choice, not because a writer happens not to exist
yet (ADR-0032). ``Application.legal_status`` arrives as a pre-frozen
snapshot (mirroring ``applicant``, ADR-0027) -- this class only ever reads
data handed to it, never loads or saves a profile file. A captured
legal-status answer is not persisted back to the profile for reuse by a
future application in this slice; that requires a ``MasterProfile`` writer
that does not exist anywhere in this codebase yet, and building one is
named, explicit, deferred future work, not folded silently into this
wiring.

Which ATS's form to fill is resolved from the opportunity's ``source_url``
via :func:`~career_agent.domain.ats_urls.resolve_ats_kind` (the same
pattern-match ADR-0019 reuses for Tier 1), dispatching to a per-``ats_kind``
:class:`~career_agent.agents.apply.form_fillers.FormFiller`
(``form_fillers.py``, ADR-0028). Only Greenhouse has a real, working
``FormFiller`` -- Lever's and Ashby's real field selectors could not be
verified against a live posting from this codebase (see that module's
docstring), so they are explicit, clearly-labeled stubs, not guessed at.

The challenge-detection and submit-click selectors are also resolved
per-``FormFiller`` (``challenge_selector``/``submit_selector``, ADR-0029)
rather than hardcoded here -- a real, live Lever posting confirmed real
hCaptcha markup (``div#h-captcha``, a hidden submit target) that the
previously hardcoded Greenhouse-fixture-shaped literals would never have
matched.

**Before clicking submit, this class still refuses outright** at any
*required* field it cannot even describe to a human -- no ``aria-label``,
no associated ``<label>``, no ``placeholder`` found at all
(:class:`UnsupportedFormFieldsError`). Handing a human a blank field with
zero context is close enough to guessing that refusing beats manifesting
it; every *describable* required field goes through Phase A's
classify-then-manifest path instead. This is a platform-agnostic,
live-DOM-verified check (queries the real page's actual form elements, not
a fixed list of "known bad" selectors), so it works the same way regardless
of which ATS's form is loaded. *Optional* fields with no unanswered
required state are left alone -- leaving an optional field blank is honest;
only a required field with no safe way to answer it blocks submission.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal, NamedTuple

from career_agent.agents.apply.field_inspection import (
    fields_still_empty as _fields_still_empty,
)
from career_agent.agents.apply.field_inspection import (
    triage_unhandled_fields as _triage_unhandled_fields,
)

# Re-exported for external callers/tests only -- unused within this module
# itself since this file's own detection now delegates to _triage_unhandled_fields.
from career_agent.agents.apply.field_inspection import (  # noqa: F401
    unhandled_required_fields as _unhandled_required_fields,
)
from career_agent.agents.apply.form_fillers import FormFiller, default_form_fillers
from career_agent.core.events import (
    ApplicationSubmitted,
    Event,
    HumanActionRequired,
)
from career_agent.core.interfaces import OpportunityRepository
from career_agent.domain.ats_urls import resolve_ats_kind
from career_agent.domain.models import (
    HumanConfirmation,
    PauseAcknowledgment,
    SubmissionPreview,
    SubmittableApplication,
)
from career_agent.integrations.browser_session import EncryptedSessionStore

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page


class NoApplicableFormFillerError(Exception):
    """No registered FormFiller applies to this opportunity.

    Fires when the opportunity isn't found, its ``source_url`` doesn't match
    a known ATS pattern, or it matches a pattern no ``FormFiller`` is
    registered for. Mirrors :class:`~career_agent.agents.apply.applicator.
    NoApplicableAdapterError` for the same reason (ADR-0019): submission
    genuinely cannot proceed, and that must be visible to the caller, not
    silently swallowed.
    """


class UnsupportedFormFieldsError(Exception):
    """A required field has no describable text at all -- refused outright.

    Raised *before* ``#submit_app`` (or its platform equivalent) is ever
    clicked, and only for a field this class cannot even show a human: no
    ``aria-label``, associated ``<label>``, or ``placeholder`` found. Every
    other required field this ``FormFiller`` doesn't already know goes
    through Phase A's classify-then-manifest path instead (ADR-0032) --
    this exception is now the narrower "cannot even describe it" case, not
    "any unknown field" (ADR-0028's original, broader scope).
    """


class UnknownPauseTokenError(Exception):
    """A resume() call named a pause_token this BrowserApplicator never issued."""


class ChallengeStillPresentError(Exception):
    """resume() was called, but the challenge is still visible on the page.

    Raised *without* re-clicking submit -- the click that would complete the
    application is never attempted again until the challenge is confirmed
    gone, checked freshly against the live page, not assumed from the
    acknowledgment alone.
    """


class RequiredFieldsStillUnresolvedError(Exception):
    """resume() was called, but a manifested Phase A field is still empty.

    Distinct from :class:`ChallengeStillPresentError` on purpose (ADR-0032)
    -- same "never trust the acknowledgment, check the live page" principle,
    generalized from one condition (challenge gone) to another (these
    specific fields non-empty), not blurred into one check. Raised without
    ever clicking submit, exactly like its Phase B counterpart.
    """


class _PausedSession(NamedTuple):
    session_id: str
    page: Page
    context: BrowserContext
    browser: Browser
    application: SubmittableApplication
    filler: FormFiller
    reason: Literal["fields_need_human_input", "challenge"]
    #: Selectors the human must fill directly on the live page before a
    #: Phase A resume() will proceed. Always empty for a "challenge" pause.
    manifest: tuple[str, ...] = ()


class BrowserApplicator:
    """Tier 2: drives a real browser through a real ATS's public apply form."""

    def __init__(
        self,
        session_store: EncryptedSessionStore,
        opportunity_repo: OpportunityRepository,
        *,
        form_fillers: dict[str, FormFiller] | None = None,
        chromium_executable_path: str | None = None,
        on_context_ready: Callable[[BrowserContext], Awaitable[None]] | None = None,
    ) -> None:
        """Configure session persistence, opportunity lookup, and Chromium.

        ``form_fillers`` defaults to :func:`~career_agent.agents.apply.
        form_fillers.default_form_fillers` (real Greenhouse, stub Lever/
        Ashby) -- injectable so tests can register a minimal or fake filler
        without depending on the real registry.

        ``chromium_executable_path`` is only needed when the installed
        Playwright/Chromium versions are mismatched (as in this sandbox);
        production use leaves it unset and lets Playwright find its own.

        ``on_context_ready`` is a test-only seam: called with the real
        ``BrowserContext`` right after it's created, before navigation. Real
        (production) use leaves this unset. Tests use it to register a
        Playwright route redirecting a real-looking ATS URL (so
        ``resolve_ats_kind`` resolves the same ``ats_kind`` a real posting
        would) to a local offline fixture, without ever making a real
        network request.
        """
        self._session_store = session_store
        self._opportunity_repo = opportunity_repo
        self._form_fillers = (
            form_fillers if form_fillers is not None else default_form_fillers()
        )
        self._chromium_executable_path = chromium_executable_path
        self._on_context_ready = on_context_ready
        self._pending: dict[
            str, tuple[SubmissionPreview, SubmittableApplication, FormFiller]
        ] = {}
        self._paused: dict[str, _PausedSession] = {}

    async def prepare(self, application: SubmittableApplication) -> SubmissionPreview:
        """Assemble what would be sent. No network/browser I/O; cannot itself submit.

        Raises :class:`NoApplicableFormFillerError` if the opportunity can't
        be resolved to a registered ``FormFiller`` -- including when it
        resolves to a real, known ``ats_kind`` whose filler is a stub (the
        stub itself only raises once ``fill_identity_and_resume`` is
        reached; this check catches an *unregistered* ``ats_kind`` earlier).
        """
        app = application.application
        opportunity = await self._opportunity_repo.get(app.opportunity_id)
        if opportunity is None:
            raise NoApplicableFormFillerError(
                f"opportunity {app.opportunity_id!r} not found -- cannot "
                f"resolve which form filler applies"
            )
        ats_kind = resolve_ats_kind(opportunity.source_url)
        filler = self._form_fillers.get(ats_kind) if ats_kind else None
        if filler is None:
            raise NoApplicableFormFillerError(
                f"no FormFiller available for opportunity {app.opportunity_id!r} "
                f"(resolved ats_kind={ats_kind!r}, registered: "
                f"{sorted(self._form_fillers)})"
            )
        preview = SubmissionPreview(
            application_id=app.id,
            tier="browser",
            target=opportunity.source_url,
            rendered_content=app.resume.rendered_text or app.resume.content.summary,
            preview_token=str(uuid.uuid4()),
        )
        self._pending[preview.preview_token] = (preview, application, filler)
        return preview

    async def submit(
        self, preview: SubmissionPreview, confirmation: HumanConfirmation
    ) -> Event:
        """Fill and submit the form, only if ``confirmation`` names this exact preview.

        Returns ``HumanActionRequired`` (not ``ApplicationSubmitted``) if
        Phase A finds unresolved fields or a Phase B challenge appears --
        the caller must obtain a
        :class:`~career_agent.domain.models.PauseAcknowledgment` and call
        ``resume()``; this method never waits for one itself.

        The real page is always closed before this method returns or raises
        -- including when ``fill_identity_and_resume`` or the unhandled-
        field check fails -- so a refusal never leaks an open browser.
        """
        pending = self._pending.get(preview.preview_token)
        if pending is None:
            raise ValueError(
                f"unknown or already-consumed preview_token "
                f"{preview.preview_token!r} -- call prepare() first"
            )
        stored_preview, application, filler = pending
        if stored_preview != preview:
            raise ValueError(
                "preview does not match the one issued by prepare() -- "
                "refusing to submit"
            )
        if confirmation.preview_token != preview.preview_token:
            raise ValueError(
                f"confirmation names preview_token "
                f"{confirmation.preview_token!r}, but this is preview "
                f"{preview.preview_token!r} -- refusing to submit an "
                f"unconfirmed preview"
            )
        del self._pending[preview.preview_token]

        session_id = application.application.opportunity_id
        page, context, browser = await self._open_page(session_id, preview.target)
        try:
            await filler.fill_identity_and_resume(page, application)
            hard_refuse, manifest = await _triage_unhandled_fields(
                page, filler.known_field_selectors, application.application.legal_status
            )
            if hard_refuse:
                raise UnsupportedFormFieldsError(
                    f"this posting's form has required field(s) "
                    f"{hard_refuse} with no describable label, aria-label, "
                    f"or placeholder -- refusing to submit rather than "
                    f"handing a human a blank, context-free field "
                    f"(ADR-0032)"
                )
        except BaseException:
            await browser.close()
            raise

        if manifest:
            pause_token = str(uuid.uuid4())
            self._paused[pause_token] = _PausedSession(
                session_id,
                page,
                context,
                browser,
                application,
                filler,
                reason="fields_need_human_input",
                manifest=tuple(field.selector for field in manifest),
            )
            return HumanActionRequired(
                correlation_id=application.application.opportunity_id,
                application_id=application.application.id,
                reason="fields_need_human_input",
            )

        return await self._click_submit_and_check_challenge(
            session_id, page, context, browser, application, filler
        )

    async def resume(self, pause_token: str, ack: PauseAcknowledgment) -> Event:
        """Continue a paused submission, only if ``ack`` names this exact pause.

        Branches on the pause's own ``reason`` (ADR-0032) -- a
        "fields_need_human_input" pause re-verifies every manifested field
        is non-empty on the live page (:class:`RequiredFieldsStillUnresolvedError`
        if not) and then performs the *first* submit click; a "challenge"
        pause re-checks the challenge is actually gone
        (:class:`ChallengeStillPresentError` if not) and re-clicks submit
        after a click that was previously blocked. Different checks for
        different reasons, not one generic re-verification -- the same
        distinction ``UnsupportedFormFieldsError`` and
        ``AmbiguousDropdownMatchError`` keep as separate types elsewhere in
        this project.
        """
        if ack.pause_token != pause_token:
            raise ValueError(
                f"acknowledgment names pause_token {ack.pause_token!r}, but "
                f"this is pause {pause_token!r} -- refusing to resume"
            )
        paused = self._paused.get(pause_token)
        if paused is None:
            raise UnknownPauseTokenError(
                f"unknown or already-consumed pause_token {pause_token!r}"
            )

        if paused.reason == "challenge":
            if await paused.page.is_visible(paused.filler.challenge_selector):
                raise ChallengeStillPresentError(
                    f"challenge is still present for pause_token "
                    f"{pause_token!r} -- not attempting to complete the "
                    f"submission"
                )
            del self._paused[pause_token]
            await paused.page.click(paused.filler.submit_selector)
            return await self._finish(
                paused.session_id,
                paused.page,
                paused.context,
                paused.browser,
                paused.application,
            )

        still_empty = await _fields_still_empty(paused.page, paused.manifest)
        if still_empty:
            raise RequiredFieldsStillUnresolvedError(
                f"pause_token {pause_token!r}: field(s) {still_empty} are "
                f"still empty on the live page -- not attempting to "
                f"complete the submission"
            )
        del self._paused[pause_token]
        return await self._click_submit_and_check_challenge(
            paused.session_id,
            paused.page,
            paused.context,
            paused.browser,
            paused.application,
            paused.filler,
        )

    async def _click_submit_and_check_challenge(
        self,
        session_id: str,
        page: Page,
        context: BrowserContext,
        browser: Browser,
        application: SubmittableApplication,
        filler: FormFiller,
    ) -> Event:
        await page.click(filler.submit_selector)

        if await page.is_visible(filler.challenge_selector):
            pause_token = str(uuid.uuid4())
            self._paused[pause_token] = _PausedSession(
                session_id, page, context, browser, application, filler,
                reason="challenge",
            )
            return HumanActionRequired(
                correlation_id=application.application.opportunity_id,
                application_id=application.application.id,
                reason="verification",
            )

        return await self._finish(session_id, page, context, browser, application)

    async def _open_page(
        self, session_id: str, target_url: str
    ) -> tuple[Page, BrowserContext, Browser]:
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            executable_path=self._chromium_executable_path
        )
        stored_state = self._session_store.load(session_id)
        context = await browser.new_context(
            storage_state=stored_state if stored_state else None
        )
        if self._on_context_ready is not None:
            await self._on_context_ready(context)
        page = await context.new_page()
        await page.goto(target_url)
        return page, context, browser

    async def _finish(
        self,
        session_id: str,
        page: Page,
        context: BrowserContext,
        browser: Browser,
        application: SubmittableApplication,
    ) -> Event:
        state = await context.storage_state()
        self._session_store.save(session_id, state)
        await browser.close()
        return ApplicationSubmitted(
            correlation_id=application.application.opportunity_id,
            application_id=application.application.id,
            tier_used="browser",
        )
