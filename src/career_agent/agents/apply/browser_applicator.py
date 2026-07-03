"""Tier 2 (browser) Applicator (ADR-0020, generalized in ADR-0028).

Same confirmation-token discipline as :class:`~career_agent.agents.apply.
applicator.TieredApplicator` (ADR-0018) for ``prepare``/``submit``, plus a
second, analogous token for the one thing Tier 1 never has to handle: a
mid-submission pause. When the driven browser hits a CAPTCHA, verification,
or login wall, ``submit`` does not wait, poll, or retry internally -- it
returns ``HumanActionRequired`` (an event type defined since Phase 2 and
unused until now) and the underlying page is held open, untouched, until a
matching :class:`~career_agent.domain.models.PauseAcknowledgment` arrives via
``resume()``. There is no timeout-based auto-continue and no way to advance
the paused session with anything other than an exact, verified match --
``resume()`` re-checks the challenge is actually gone before ever touching
the page again, rather than trusting the acknowledgment alone.

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

**Before clicking submit, this class refuses rather than guesses** at any
*required* form field a ``FormFiller`` doesn't declare knowing how to fill
(:class:`UnsupportedFormFieldsError`) -- a custom question, an EEOC/
demographic question, anything else. This is a platform-agnostic,
live-DOM-verified check (queries the real page's actual form elements, not
a fixed list of "known bad" selectors), so it works the same way regardless
of which ATS's form is loaded. *Optional* fields with no unanswered
required state are left alone -- leaving an optional field blank is honest;
only a required field with no safe way to answer it blocks submission.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, NamedTuple

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
    """The live form has a required field this FormFiller can't safely fill.

    Raised *before* ``#submit_app`` (or its platform equivalent) is ever
    clicked -- a custom question, an EEOC/demographic question, or anything
    else outside identity + resume is never guessed at, confirmed, or
    left for a human to react to after the fact. The only acceptable
    behaviors for a field this project cannot honestly answer are: it stays
    unfilled because the form permits that, or a human answers it directly
    -- never a system-originated guess (ADR-0028).
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


class _PausedSession(NamedTuple):
    session_id: str
    page: Page
    context: BrowserContext
    browser: Browser
    application: SubmittableApplication
    filler: FormFiller


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

        Returns ``HumanActionRequired`` (not ``ApplicationSubmitted``) if a
        challenge appears -- the caller must obtain a
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
            unhandled = await _unhandled_required_fields(
                page, filler.known_field_selectors
            )
            if unhandled:
                raise UnsupportedFormFieldsError(
                    f"this posting's form has required field(s) "
                    f"{unhandled} that {type(filler).__name__} does not "
                    f"know how to safely fill -- refusing to submit "
                    f"(ADR-0028)"
                )
        except BaseException:
            await browser.close()
            raise

        await page.click(filler.submit_selector)

        if await page.is_visible(filler.challenge_selector):
            pause_token = str(uuid.uuid4())
            self._paused[pause_token] = _PausedSession(
                session_id, page, context, browser, application, filler
            )
            return HumanActionRequired(
                correlation_id=application.application.opportunity_id,
                application_id=application.application.id,
                reason="verification",
            )

        return await self._finish(session_id, page, context, browser, application)

    async def resume(self, pause_token: str, ack: PauseAcknowledgment) -> Event:
        """Continue a paused submission, only if ``ack`` names this exact pause.

        Re-checks the challenge is actually gone on the live page before
        clicking anything -- raises :class:`ChallengeStillPresentError`
        without touching the page again if it's still visible.
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
        if await paused.page.is_visible(paused.filler.challenge_selector):
            raise ChallengeStillPresentError(
                f"challenge is still present for pause_token {pause_token!r} "
                f"-- not attempting to complete the submission"
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


async def _unhandled_required_fields(
    page: Page, known_field_selectors: frozenset[str]
) -> list[str]:
    """Return every required form field a FormFiller doesn't know how to fill.

    Queried generically against the real page's actual ``form`` elements
    (not a fixed per-platform list), so this works the same way regardless
    of which ATS's form is loaded -- it is the mechanism, not per-platform
    knowledge, that makes the refusal possible. Submit/button/hidden inputs
    are never data fields, so they are excluded; a field with no
    ``required`` attribute is left alone -- an optional field left blank is
    honest, only an unanswerable *required* field blocks submission.

    Each element's own real selector is derived from whichever attribute it
    actually has -- ``#id`` first, then ``[name='...']`` (ADR-0029): a real
    Lever posting confirmed identity fields with no ``id`` at all, only
    ``name``, so ``known_field_selectors`` must be compared against
    whichever shape the live page actually uses, not assumed to always be
    ``#id``.
    """
    elements = await page.query_selector_all("form input, form textarea, form select")
    unhandled: list[str] = []
    for element in elements:
        input_type = (await element.get_attribute("type")) or ""
        if input_type.lower() in {"submit", "button", "hidden"}:
            continue
        if await element.get_attribute("required") is None:
            continue
        element_id = await element.get_attribute("id")
        name = await element.get_attribute("name")
        if element_id:
            selector = f"#{element_id}"
        elif name:
            selector = f"[name='{name}']"
        else:
            selector = None
        if selector is not None and selector in known_field_selectors:
            continue
        unhandled.append(selector if selector is not None else "(no id or name)")
    return unhandled
