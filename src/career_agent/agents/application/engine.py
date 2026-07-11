"""Application Preparation Engine (Phase 51, ADR-0069): prepare, then STOP.

Composes exactly the infrastructure Phases 47/48/50 already built --
``BrowserManager``/``TabManager``/``SessionManager`` (Phase 47), provider
detection (Phase 48's ``resolve_ats_kind``/``AdapterRegistry``), and a
:class:`~career_agent.agents.apply.form_fillers.FormFiller` plus the field
detection/classification/auto-answer machinery
(:mod:`career_agent.agents.apply.field_inspection`,
:mod:`career_agent.agents.apply.question_answerer`) that already back Tier 2
of the (unwired) apply pipeline (ADR-0020/0028/0031/0032). **The one and
only behavioral difference from that existing machinery: this engine never
clicks anything.** This module never reads a FormFiller's clickable-action
selector at all, and source-scan tests in
``tests/agents/test_application_engine.py`` prove it, the same
structural-guarantee discipline ``SessionManager``'s login-safety test
already established for "never types a credential."

Every field this engine cannot safely resolve (no known selector, no
captured profile fact, no describable label) is recorded in
``ApplicationSession.missing_fields`` for a human to fill directly --
nothing is guessed, nothing is invented. See ADR-0069 for the full
audit trail of what already existed vs. what Phase 51 actually adds.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from career_agent.agents.apply.field_inspection import triage_unhandled_fields
from career_agent.agents.apply.form_fillers import FormFiller, default_form_fillers
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.ats_urls import resolve_ats_kind
from career_agent.domain.cover_letter import TailoredCoverLetter
from career_agent.domain.models import Application, Opportunity, SubmittableApplication
from career_agent.integrations.adapters.base import FeatureUnavailableError
from career_agent.integrations.browser.browser_manager import BrowserManager
from career_agent.integrations.browser.session_manager import (
    LoginTimeoutError,
    SessionManager,
)
from career_agent.integrations.browser.tab_manager import TabManager

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page


class ApplicationPreparationEngine:
    """Opens a real browser, fills what it safely can, and stops before Submit."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        session_manager: SessionManager,
        *,
        form_fillers: dict[str, FormFiller] | None = None,
        on_context_ready: Callable[[BrowserContext], Awaitable[None]] | None = None,
        headless: bool = False,
    ) -> None:
        """Wrap already-configured Phase 47 infrastructure.

        ``form_fillers`` defaults to
        :func:`~career_agent.agents.apply.form_fillers.default_form_fillers`
        (real Greenhouse, real Lever, honest Ashby stub) -- the exact same
        registry ``BrowserApplicator`` uses, unmodified.

        ``on_context_ready`` is a test-only seam, the identical shape
        ``BrowserApplicator`` already uses (ADR-0020): called with the real
        ``BrowserContext`` right after it's created, before navigation.
        Real (production) use leaves this unset; tests use it to route a
        real-looking ATS URL to a local offline fixture, without ever
        making a real network request.

        ``headless`` defaults to ``False`` -- matching
        :class:`~career_agent.integrations.browser.browser_manager.
        BrowserManager`'s own default, since a human may need to see and
        log into the window. Tests (which run in a display-less sandbox)
        set this ``True``.
        """
        self._browser_manager = browser_manager
        self._session_manager = session_manager
        self._headless = headless
        self._form_fillers = (
            form_fillers if form_fillers is not None else default_form_fillers()
        )
        self._on_context_ready = on_context_ready

    async def build_session(
        self,
        opportunity: Opportunity,
        application: SubmittableApplication,
        *,
        cover_letter: TailoredCoverLetter | None = None,
        resume_variant_id: str | None = None,
        login_indicator_selector: str | None = None,
        login_timeout_seconds: float = 300.0,
    ) -> ApplicationSession:
        """Prepare one application and return a reviewable, unsubmitted session.

        Raises :class:`~career_agent.integrations.adapters.base.
        FeatureUnavailableError` before ever opening a browser if no
        :class:`~career_agent.agents.apply.form_fillers.FormFiller` is
        registered for this opportunity's platform at all -- the same
        fail-fast precondition check ``BrowserApplicator.prepare()``
        already applies for the same reason (ADR-0019's pattern, reused).

        ``login_indicator_selector`` is caller-supplied, exactly like
        :meth:`~career_agent.integrations.browser.session_manager.
        SessionManager.wait_for_login` requires (Phase 47): this project
        has no verified "logged in" selector for any platform yet. When
        ``None``, login state is never checked -- a warning records that
        gap rather than silently assuming either logged-in or logged-out.
        """
        # The *browser* session (login/cookies) is keyed by opportunity,
        # not a fresh random id, so a second run against the same
        # opportunity reuses saved state instead of always starting logged
        # out -- the same keying ``BrowserApplicator`` already uses. This
        # is distinct from ``record_id`` below (the returned
        # ``ApplicationSession``'s own identity): every preparation
        # *attempt* still gets a fresh id, the same "append-only audit
        # trail" shape ``SqliteApplicationStore`` already uses.
        browser_session_id = opportunity.id
        record_id = str(uuid.uuid4())
        app = application.application
        ats_kind = resolve_ats_kind(opportunity.source_url)
        filler = self._form_fillers.get(ats_kind) if ats_kind else None
        if filler is None:
            raise FeatureUnavailableError(
                f"no FormFiller available for opportunity {opportunity.id!r} "
                f"(resolved ats_kind={ats_kind!r}, registered: "
                f"{sorted(self._form_fillers)}) -- cannot prepare an "
                f"application for this platform yet"
            )

        warnings: list[str] = []
        if cover_letter is not None:
            warnings.append(
                "cover_letter_upload_unsupported: no platform has a "
                "verified cover-letter form field yet (ADR-0069) -- the "
                "cover letter is available on this session for manual "
                "attachment during review, not auto-uploaded"
            )
        if login_indicator_selector is None:
            warnings.append(
                "login_detection_skipped: no login_indicator_selector was "
                "supplied -- this project has no verified logged-in "
                "selector for any platform yet"
            )

        browser = await self._browser_manager.launch(headless=self._headless)
        context = await browser.new_context(
            storage_state=self._session_manager.load(browser_session_id)
        )
        if self._on_context_ready is not None:
            await self._on_context_ready(context)
        tabs = TabManager(context)
        try:
            page: Page = await tabs.open_tab("application", url=opportunity.source_url)

            if login_indicator_selector is not None:
                try:
                    await self._session_manager.wait_for_login(
                        page,
                        login_indicator_selector,
                        timeout_seconds=login_timeout_seconds,
                    )
                except LoginTimeoutError:
                    return self._build_result(
                        record_id,
                        opportunity,
                        "LOGIN_REQUIRED_TIMEOUT",
                        resume_variant_id,
                        cover_letter,
                        warnings=[*warnings, "login was never detected"],
                    )

            await filler.fill_identity_and_resume(page, application)
            uploaded_files = await _uploaded_resume_paths(app, filler)
            hard_refuse, manifest = await triage_unhandled_fields(
                page, filler.known_field_selectors, app.legal_status
            )
            await self._session_manager.save(browser_session_id, context)
        finally:
            await context.close()

        status = "BLOCKED" if hard_refuse else "READY_FOR_REVIEW"
        missing = [*hard_refuse, *(field.selector for field in manifest)]
        filled = sorted(filler.known_field_selectors)
        detected = sorted({*filled, *missing})
        return self._build_result(
            record_id,
            opportunity,
            status,
            resume_variant_id,
            cover_letter,
            warnings=warnings,
            filled_fields=filled,
            detected_fields=detected,
            missing_fields=missing,
            uploaded_files=uploaded_files,
        )

    def _build_result(
        self,
        session_id: str,
        opportunity: Opportunity,
        status: str,
        resume_variant_id: str | None,
        cover_letter: TailoredCoverLetter | None,
        *,
        warnings: list[str],
        filled_fields: list[str] | None = None,
        detected_fields: list[str] | None = None,
        missing_fields: list[str] | None = None,
        uploaded_files: list[str] | None = None,
    ) -> ApplicationSession:
        return ApplicationSession(
            id=session_id,
            provider=resolve_ats_kind(opportunity.source_url) or "unknown",
            company=opportunity.canonical_company,
            job_title=opportunity.title,
            url=opportunity.source_url,
            opportunity_id=opportunity.id,
            status=status,  # type: ignore[arg-type]
            resume_variant_id=resume_variant_id,
            cover_letter_body=cover_letter.body if cover_letter is not None else None,
            filled_fields=filled_fields or [],
            detected_fields=detected_fields or [],
            missing_fields=missing_fields or [],
            uploaded_files=uploaded_files or [],
            warnings=warnings,
            created_at=datetime.now(UTC),
        )


async def _uploaded_resume_paths(app: Application, filler: FormFiller) -> list[str]:
    """Real files this filler actually attached via ``set_input_files``.

    Grounded in the same evidence ``AdapterCapabilities`` already declares
    (Phase 48): Lever's résumé field is a verified required file upload;
    Greenhouse's is a verified plain text field (nothing uploaded). Never
    guessed -- this only ever reports what ``FormFiller.fill_identity_and_resume``
    is independently documented (ADR-0035) to have already attached.
    """
    if filler.ats_kind != "lever":
        return []
    docx = next(
        (
            artifact
            for artifact in app.resume.artifacts
            if artifact.format == "docx"
        ),
        None,
    )
    return [docx.path] if docx is not None else []
