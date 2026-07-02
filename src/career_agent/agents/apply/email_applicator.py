"""Tier 3 (email) Applicator: draft-only, never sends (ADR-0021).

Same confirmation-token discipline as :class:`~career_agent.agents.apply.
applicator.TieredApplicator` (ADR-0018) for ``prepare``/``submit``, applied
to a tier that structurally cannot complete the way Tier 1/2 do.
:class:`~career_agent.core.interfaces.EmailDraftSink` has no ``send`` method
at all -- so ``submit`` here can only ever create a draft and hand control
to the human. It never returns ``ApplicationSubmitted``: claiming a resume
was submitted when it is actually sitting unsent in a draft would be the
truthfulness problem ADR-0003 exists to prevent, relocated from resume
content to this system's own claims about its actions. It returns
``HumanActionRequired(reason="confirmation")`` instead -- the application
belongs in ``status="paused_for_human"``, permanently (no ``resume()``
exists for this tier; see the note on ``Application.status``, ADR-0021).

Confirming a drafted email was actually sent is a distinct, separate
problem (polling the mailbox, matching a sent message back to a specific
draft) and is explicitly out of scope for this slice -- named, tracked, and
tied to the same trigger as the profile-staleness gap (ADR-0018): it must
close before any scheduled/autonomous apply run, not before then.
"""

from __future__ import annotations

import uuid

from career_agent.core.events import Event, HumanActionRequired
from career_agent.core.interfaces import EmailDraftSink, OpportunityRepository
from career_agent.domain.models import (
    HumanConfirmation,
    SubmissionPreview,
    SubmittableApplication,
)


class EmailApplicator:
    """Tier 3: creates a draft email via an injected :class:`EmailDraftSink`."""

    def __init__(
        self, draft_sink: EmailDraftSink, opportunity_repo: OpportunityRepository
    ) -> None:
        """Configure the draft sink and opportunity lookup."""
        self._draft_sink = draft_sink
        self._opportunity_repo = opportunity_repo
        self._pending: dict[
            str, tuple[SubmissionPreview, SubmittableApplication]
        ] = {}

    async def prepare(self, application: SubmittableApplication) -> SubmissionPreview:
        """Assemble what would be drafted. No I/O; cannot itself create a draft.

        ``target`` is the recipient address, resolved from the opportunity's
        ``source_url`` -- a real "apply by email" address is not modeled
        anywhere in ``Opportunity`` yet (a named gap: this slice does not
        solve recipient-address discovery, only draft-creation once a
        target is known).
        """
        app = application.application
        opportunity = await self._opportunity_repo.get(app.opportunity_id)
        if opportunity is None:
            raise ValueError(
                f"opportunity {app.opportunity_id!r} not found -- cannot "
                f"resolve a recipient address"
            )
        preview = SubmissionPreview(
            application_id=app.id,
            tier="email",
            target=opportunity.source_url,
            rendered_content=app.resume.rendered_text or app.resume.content.summary,
            preview_token=str(uuid.uuid4()),
        )
        self._pending[preview.preview_token] = (preview, application)
        return preview

    async def submit(
        self, preview: SubmissionPreview, confirmation: HumanConfirmation
    ) -> Event:
        """Create the draft, only if ``confirmation`` names this exact preview.

        Always returns ``HumanActionRequired`` -- never
        ``ApplicationSubmitted`` -- because creating a draft is the most
        this tier can ever honestly claim to have done.
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
                "refusing to create a draft"
            )
        if confirmation.preview_token != preview.preview_token:
            raise ValueError(
                f"confirmation names preview_token "
                f"{confirmation.preview_token!r}, but this is preview "
                f"{preview.preview_token!r} -- refusing to create an "
                f"unconfirmed draft"
            )
        del self._pending[preview.preview_token]

        await self._draft_sink.create_draft(
            to=preview.target,
            subject=f"Application: {application.application.opportunity_id}",
            body=preview.rendered_content,
        )
        return HumanActionRequired(
            correlation_id=application.application.opportunity_id,
            application_id=application.application.id,
            reason="confirmation",
        )
