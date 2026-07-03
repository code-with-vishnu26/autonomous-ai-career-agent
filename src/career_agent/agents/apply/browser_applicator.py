"""Tier 2 (browser) Applicator, Greenhouse's public apply form only (ADR-0020).

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

Scope: this class only knows Greenhouse's public apply-form field shape and
resolves the form URL directly from the opportunity's ``source_url``.
Generalizing to arbitrary company career pages is real, separate future
work (ADR-0020), the same way Greenhouse-first proved the ATS contract in
Phase 4a before Lever/Ashby were added.

``_fill_form`` (Phase 8f, ADR-0027) fills the form's identity fields from
``application.application.applicant`` -- a frozen ``BasicsSection`` snapshot
now carried on every ``Application`` -- rather than the placeholder literal
strings this class filled with before that field existed. ``_split_name``
below is a documented, known-imprecise stopgap for turning one JSON-Resume
``name`` string into Greenhouse's separate first/last fields; real
correctness needs per-field human confirmation, not a smarter heuristic,
and stays named, deferred future work.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, NamedTuple

from career_agent.core.events import (
    ApplicationSubmitted,
    Event,
    HumanActionRequired,
)
from career_agent.core.interfaces import OpportunityRepository
from career_agent.domain.models import (
    HumanConfirmation,
    PauseAcknowledgment,
    SubmissionPreview,
    SubmittableApplication,
)
from career_agent.integrations.browser_session import EncryptedSessionStore

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page


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


class BrowserApplicator:
    """Tier 2: drives a real browser through Greenhouse's public apply form."""

    def __init__(
        self,
        session_store: EncryptedSessionStore,
        opportunity_repo: OpportunityRepository,
        *,
        chromium_executable_path: str | None = None,
    ) -> None:
        """Configure session persistence, opportunity lookup, and Chromium.

        ``chromium_executable_path`` is only needed when the installed
        Playwright/Chromium versions are mismatched (as in this sandbox);
        production use leaves it unset and lets Playwright find its own.
        """
        self._session_store = session_store
        self._opportunity_repo = opportunity_repo
        self._chromium_executable_path = chromium_executable_path
        self._pending: dict[
            str, tuple[SubmissionPreview, SubmittableApplication]
        ] = {}
        self._paused: dict[str, _PausedSession] = {}

    async def prepare(self, application: SubmittableApplication) -> SubmissionPreview:
        """Assemble what would be sent. No network/browser I/O; cannot itself submit."""
        app = application.application
        opportunity = await self._opportunity_repo.get(app.opportunity_id)
        if opportunity is None:
            raise ValueError(
                f"opportunity {app.opportunity_id!r} not found -- cannot "
                f"resolve the apply-form URL"
            )
        preview = SubmissionPreview(
            application_id=app.id,
            tier="browser",
            target=opportunity.source_url,
            rendered_content=app.resume.rendered_text or app.resume.content.summary,
            preview_token=str(uuid.uuid4()),
        )
        self._pending[preview.preview_token] = (preview, application)
        return preview

    async def submit(
        self, preview: SubmissionPreview, confirmation: HumanConfirmation
    ) -> Event:
        """Fill and submit the form, only if ``confirmation`` names this exact preview.

        Returns ``HumanActionRequired`` (not ``ApplicationSubmitted``) if a
        challenge appears -- the caller must obtain a
        :class:`~career_agent.domain.models.PauseAcknowledgment` and call
        ``resume()``; this method never waits for one itself.
        """
        pending = self._pending.get(preview.preview_token)
        if pending is None:
            raise ValueError(
                f"unknown or already-consumed preview_token "
                f"{preview.preview_token!r} -- call prepare() first"
            )
        stored_preview, application = pending
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
        await self._fill_form(page, application)
        await page.click("#submit_app")

        if await page.is_visible("#verification-challenge"):
            pause_token = str(uuid.uuid4())
            self._paused[pause_token] = _PausedSession(
                session_id, page, context, browser, application
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
        if await paused.page.is_visible("#verification-challenge"):
            raise ChallengeStillPresentError(
                f"challenge is still present for pause_token {pause_token!r} "
                f"-- not attempting to complete the submission"
            )
        del self._paused[pause_token]
        await paused.page.click("#submit_app")
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
        page = await context.new_page()
        await page.goto(target_url)
        return page, context, browser

    async def _fill_form(self, page: Page, application: SubmittableApplication) -> None:
        applicant = application.application.applicant
        first_name, last_name = _split_name(applicant.name)
        summary = application.application.resume.content.summary
        await page.fill("#first_name", first_name)
        await page.fill("#last_name", last_name)
        await page.fill("#email", applicant.email)
        await page.fill("#resume_text", summary)

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


def _split_name(name: str) -> tuple[str, str]:
    """Split one JSON-Resume ``basics.name`` into Greenhouse's first/last fields.

    A **known-imprecise stopgap, not an assumed-correct split** (ADR-0027):
    the last whitespace-separated token becomes ``last_name``, everything
    before it becomes ``first_name``; a single-token name puts that token in
    ``first_name`` with an empty ``last_name``. It gets multi-part surnames
    ("van der Berg"), suffixes ("Jr.", "III"), and non-Western name orders
    wrong. Solving this properly needs per-field human confirmation before a
    real submission, not a smarter heuristic -- that is named, deferred
    future work (ADR-0027), not something silently left for later.
    """
    parts = name.rsplit(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]
