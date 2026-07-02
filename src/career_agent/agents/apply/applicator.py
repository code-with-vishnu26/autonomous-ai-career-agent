"""The concrete Tier-1-only Applicator (ADR-0018, ADR-0019).

This slice proves the submission safety machinery end-to-end: structural
approval (``SubmittableApplication``, enforced in ``domain/models.py``, not
here) and confirmation-token binding (enforced here, in ``submit``).
``TieredApplicator`` resolves which registered :class:`ATSAdapter` applies to
a given opportunity from its ``source_url`` (ADR-0019, reusing the same
pattern-match ADR-0015 built for web search) -- but it still wraps only Tier
1. Tier 2 (browser) and Tier 3 (email) don't exist yet, so there is nothing
to fall back to: an opportunity with no matching or no registered adapter is
an explicit, typed failure to *prepare* (:class:`NoApplicableAdapterError`),
not a silent no-op. That is a named, tracked scope boundary (ROADMAP,
ADR-0018/0019), not an oversight.

Cross-tier fallback, when Tier 2/3 exist, is **not** built into this class
and never will be automatic here (ADR-0019): a ``HumanConfirmation`` names
one exact tier, target, and content shape, so falling back from Tier 1 to a
different tier is a materially different real-world action and must go
through its own ``prepare()``/confirm/``submit()`` cycle, requiring its own
confirmation -- an orchestration layer above this one (a future Apply Agent)
decides whether and how to retry a failed tier; ``TieredApplicator`` itself
only ever executes the one confirmed action it was given.
"""

from __future__ import annotations

import uuid

from career_agent.core.events import ApplicationFailed, Event
from career_agent.core.interfaces import ATSAdapter, OpportunityRepository
from career_agent.domain.ats_urls import resolve_ats_kind
from career_agent.domain.models import (
    HumanConfirmation,
    SubmissionPreview,
    SubmittableApplication,
)


class NoApplicableAdapterError(Exception):
    """No Tier 1 adapter applies to this opportunity, so it cannot be prepared.

    Fires when the opportunity isn't found, its ``source_url`` doesn't match
    a known ATS pattern, or it matches a pattern this ``TieredApplicator``
    has no adapter registered for. With only Tier 1 built, this means
    submission genuinely cannot proceed right now -- there is no fallback
    tier to try yet. Never silently swallowed into an empty/failed result;
    the caller must see this to eventually retry via a different tier once
    one exists (ADR-0019).
    """


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
    """Tier 1 only this slice (ADR-0018, ADR-0019).

    Confirmation-token binding is the load-bearing guarantee here: ``submit``
    refuses to call the adapter at all unless ``confirmation.preview_token``
    matches the exact preview ``prepare`` issued -- a mismatch or replay
    never reaches ``ATSAdapter``.
    """

    def __init__(
        self,
        ats_adapters: dict[str, ATSAdapter],
        opportunity_repo: OpportunityRepository,
    ) -> None:
        """Wrap the registered Tier 1 adapters, keyed by ``ats_kind``.

        ``opportunity_repo`` resolves an application's opportunity so its
        ``source_url`` can be pattern-matched to an ``ats_kind`` (ADR-0019) --
        no separate ``CompanyRepository`` is introduced for this; the same
        already-proven, already-tested pattern-match ADR-0015 built for web
        search is reused rather than a new persistence layer speculatively
        built ahead of an actual need.
        """
        self._ats_adapters = ats_adapters
        self._opportunity_repo = opportunity_repo
        self._pending: dict[
            str, tuple[SubmissionPreview, SubmittableApplication, ATSAdapter]
        ] = {}

    async def prepare(self, application: SubmittableApplication) -> SubmissionPreview:
        """Assemble what would be sent. No network I/O; cannot itself submit.

        Raises :class:`NoApplicableAdapterError` if the opportunity can't be
        resolved to a registered Tier 1 adapter -- with only Tier 1 built,
        that means preparation genuinely cannot proceed.
        """
        app = application.application
        opportunity = await self._opportunity_repo.get(app.opportunity_id)
        if opportunity is None:
            raise NoApplicableAdapterError(
                f"opportunity {app.opportunity_id!r} not found -- cannot "
                f"resolve which ATS adapter applies"
            )
        ats_kind = resolve_ats_kind(opportunity.source_url)
        adapter = self._ats_adapters.get(ats_kind) if ats_kind else None
        if adapter is None:
            raise NoApplicableAdapterError(
                f"no Tier 1 adapter available for opportunity "
                f"{app.opportunity_id!r} (resolved ats_kind={ats_kind!r}, "
                f"registered: {sorted(self._ats_adapters)})"
            )
        preview = SubmissionPreview(
            application_id=app.id,
            tier="ats_api",
            target=adapter.ats_kind,
            rendered_content=app.resume.rendered_text or app.resume.content.summary,
            preview_token=str(uuid.uuid4()),
        )
        self._pending[preview.preview_token] = (preview, application, adapter)
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
        stored_preview, application, adapter = pending
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
            return await adapter.submit(application)
        except SubmissionError as exc:
            return ApplicationFailed(
                correlation_id=application.application.opportunity_id,
                application_id=application.application.id,
                tier_attempted=preview.tier,
                error_category=exc.category,
            )

