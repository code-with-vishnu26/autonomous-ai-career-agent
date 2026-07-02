"""The concrete :class:`Applicator` — Tier 1 (direct ATS API) only (ADR-0018).

This slice proves the submission safety machinery end-to-end: structural
approval (``SubmittableApplication``, enforced in ``domain/models.py``, not
here) and confirmation-token binding (enforced here, in ``submit``). Tier
selection/fallback across ATS API -> browser -> email (ADR-0010) and
company/ATS-kind resolution are explicitly **not** built in this slice --
``TieredApplicator`` wraps exactly one injected :class:`ATSAdapter` and
always targets it. That is a named, tracked scope boundary (ROADMAP,
ADR-0018), not an oversight: it lets the safety guarantees be built and
proven correct before the tier-selection logic ADR-0010 itself flags as
possibly warranting its own future ADR is added on top.
"""

from __future__ import annotations

import uuid

from career_agent.core.events import ApplicationFailed, Event
from career_agent.core.interfaces import ATSAdapter
from career_agent.domain.models import (
    HumanConfirmation,
    SubmissionPreview,
    SubmittableApplication,
)


class SubmissionError(Exception):
    """A real ATS-side submission failure -- an expected outcome, not a bug.

    Covers cases like duplicate submission, rate limiting, or a malformed
    payload. ``category`` becomes ``ApplicationFailed.error_category``.
    """

    def __init__(self, category: str, message: str) -> None:
        """Store the failure category alongside the standard exception message."""
        super().__init__(message)
        self.category = category


class TieredApplicator:
    """Tier 1 only this slice (ADR-0018).

    Confirmation-token binding is the load-bearing guarantee here: ``submit``
    refuses to call the adapter at all unless ``confirmation.preview_token``
    matches the exact preview ``prepare`` issued -- a mismatch or replay
    never reaches ``ATSAdapter``.
    """

    def __init__(self, ats_adapter: ATSAdapter) -> None:
        """Wrap a single ATS adapter -- multi-tier fallback is a later slice."""
        self._ats_adapter = ats_adapter
        self._pending: dict[str, tuple[SubmissionPreview, SubmittableApplication]] = {}

    async def prepare(self, application: SubmittableApplication) -> SubmissionPreview:
        """Assemble what would be sent. No network I/O; cannot itself submit."""
        app = application.application
        preview = SubmissionPreview(
            application_id=app.id,
            tier="ats_api",
            target=self._ats_adapter.ats_kind,
            rendered_content=app.resume.rendered_text or app.resume.content.summary,
            preview_token=str(uuid.uuid4()),
        )
        self._pending[preview.preview_token] = (preview, application)
        return preview

    async def submit(
        self, preview: SubmissionPreview, confirmation: HumanConfirmation
    ) -> Event:
        """Send ``preview``, only if ``confirmation`` names that exact preview.

        Raises on an unknown/already-consumed token, a preview that doesn't
        match the one ``prepare`` issued, or a confirmation naming a
        different token -- none of these are legitimate submission outcomes,
        so none of them produce an ``ApplicationFailed`` event; they are
        programming/misuse errors the caller must not be able to paper over.
        A genuine ATS-side failure (``SubmissionError``), by contrast, *is* a
        legitimate outcome and becomes ``ApplicationFailed``.
        """
        pending = self._pending.get(preview.preview_token)
        if pending is None:
            raise ValueError(
                f"unknown or already-consumed preview_token "
                f"{preview.preview_token!r} -- call prepare() first, and "
                f"never submit the same preview twice"
            )
        stored_preview, application = pending
        if stored_preview != preview:
            raise ValueError(
                "preview does not match the one issued by prepare() for "
                "this token -- refusing to submit"
            )
        if confirmation.preview_token != preview.preview_token:
            raise ValueError(
                f"confirmation names preview_token "
                f"{confirmation.preview_token!r}, but this is preview "
                f"{preview.preview_token!r} -- refusing to submit an "
                f"unconfirmed preview"
            )
        # One-shot: consumed before the network call, so a raised
        # SubmissionError still leaves the token unusable for a retry-via-
        # replay -- a genuine retry must go through prepare() again.
        del self._pending[preview.preview_token]
        try:
            return await self._ats_adapter.submit(application)
        except SubmissionError as exc:
            return ApplicationFailed(
                correlation_id=application.application.opportunity_id,
                application_id=application.application.id,
                tier_attempted=preview.tier,
                error_category=exc.category,
            )

