"""Real confirmation meets a real Applicator, for the first time (ADR-0024).

Every structural guarantee this project has built through Phase 8 --
``SubmittableApplication``, token-bound ``HumanConfirmation``, the
truthfulness gate behind both -- has only ever been exercised against
fakes. This is the first slice where a real confirmation source (see
``cli.confirm_submission``) can drive a real ``Applicator`` call.

Single-tier this slice: wired against exactly one concrete ``Applicator``
(``TieredApplicator``, for an ATS-sourced opportunity) -- the same "prove
one path first" discipline as Greenhouse-first (4a), Tier-1-only (7a), and
Greenhouse's-form-only (7b3). Multi-tier selection across
``TieredApplicator``/``BrowserApplicator``/``EmailApplicator`` is real,
separate, deferred work: today three independent ``Applicator``
implementations exist with nothing that chooses between them -- ADR-0010's
"tier selection is an internal strategy this implementation chooses
between" describes a component that was never actually built. Building
that selector is genuine design work, not composition, and does not belong
in this slice.
"""

from __future__ import annotations

from collections.abc import Callable

from career_agent.core.events import Event
from career_agent.core.interfaces import Applicator
from career_agent.domain.models import (
    HumanConfirmation,
    SubmissionPreview,
    SubmittableApplication,
)


class SubmissionPipeline:
    """Prepare, obtain a real confirmation, submit -- or abort cleanly."""

    def __init__(
        self,
        applicator: Applicator,
        confirm: Callable[[SubmissionPreview], HumanConfirmation | None],
    ) -> None:
        """Configure the pipeline with a single ``Applicator`` and a confirmer.

        ``confirm`` is injected so the real, interactive
        ``cli.confirm_submission`` and a fake, scripted one in tests satisfy
        the exact same call shape -- this class never knows or cares
        whether a human or a test answered.
        """
        self._applicator = applicator
        self._confirm = confirm

    async def run(self, submittable: SubmittableApplication) -> Event | None:
        """Prepare a submission, ask for confirmation, and submit if granted.

        Returns ``None`` -- and never calls ``submit()`` -- if ``confirm``
        declines (returns ``None``). A declined confirmation is not an
        error: the human said no, and that is a legitimate, final outcome
        for this call, not something to retry or paper over.
        """
        preview = await self._applicator.prepare(submittable)
        confirmation = self._confirm(preview)
        if confirmation is None:
            return None
        return await self._applicator.submit(preview, confirmation)
