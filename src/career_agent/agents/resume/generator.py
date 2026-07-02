"""The concrete, LLM-backed :class:`ResumeGenerator` (ADR-0022).

Implements the Phase 2 ``ResumeGenerator`` Protocol (``core/interfaces.py``,
unchanged by this phase) using an injected :class:`ContentDrafter`. Mirrors
``gate.py``'s orchestration/judgment split exactly: this class decides *what*
the drafter is asked for and *how* the result is assembled into a full draft;
the drafter decides the actual wording and selection.

Design commitments (ADR-0022):

- **``summary`` is never LLM-generated.** Sourced read-only from
  ``profile.basics.summary`` -- the drafter is never asked for one, and
  :class:`~career_agent.domain.models.DraftedTailoring` has no field to carry
  one even if it tried. Resolves the gap ADR-0016 named and left open,
  structurally, the same move as ``TailoredWorkEntry`` having no date
  fields (ADR-0016's Case #6 correction).
- **A missing ``profile.basics.summary`` is a loud, explicit rejection, not
  a silently-derived fallback.** A structurally-derived one-liner (e.g.
  "Name -- Position at Company") would be zero-invention but would produce
  an obviously templated, low-quality resume -- a quality-over-volume
  failure, not a truthfulness one, but this project treats "technically
  fine, quietly worse than what the user would want" as a failure mode in
  its own right (the same shape as the 4c search-confidence problem). The
  cost of asking the user to fill in one profile field is preferred over a
  silently degraded application.
- **No self-verification, no auto-retry-on-rejection.** This class does not
  filter or validate the drafter's output against the profile before
  returning it -- that would blur the ADR-0003 split (a generator must not
  approve its own output). The gate is the sole, independent backstop. A
  draft the gate blocks is not automatically regenerated; that is separate,
  named future work.
"""

from __future__ import annotations

from career_agent.core.interfaces import ContentDrafter
from career_agent.domain.models import (
    MasterProfile,
    Opportunity,
    TailoredContent,
    TailoredResumeDraft,
)


class MissingSummaryError(Exception):
    """``profile.basics.summary`` is empty, so tailoring cannot proceed.

    Raised before the drafter is ever called (fixable by the user in
    seconds; not worth spending an LLM call on a draft that can't be
    assembled). Never silently defaulted to a derived placeholder --
    ADR-0022's quality-over-volume reasoning.
    """


class LLMResumeGenerator:
    """The concrete resume generator, backed by an injected :class:`ContentDrafter`."""

    def __init__(self, drafter: ContentDrafter) -> None:
        """Configure the generator with a drafter."""
        self._drafter = drafter

    async def tailor(
        self, opportunity: Opportunity, profile: MasterProfile
    ) -> TailoredResumeDraft:
        """Produce an unverified, structured draft for ``opportunity``.

        Raises :class:`MissingSummaryError` before calling the drafter if
        ``profile.basics.summary`` is empty -- never proceeds with a
        fallback the drafter or this class invented.
        """
        summary = profile.basics.summary
        if not summary or not summary.strip():
            raise MissingSummaryError(
                "profile.basics.summary is empty -- add a summary to your "
                "master profile before tailoring a resume. This project "
                "does not auto-generate one: a derived placeholder would "
                "produce an obviously templated, low-quality resume."
            )

        drafted = await self._drafter.draft(opportunity, profile)
        content = TailoredContent(
            summary=summary,
            work=drafted.work,
            skills=drafted.skills,
            projects=drafted.projects,
        )
        return TailoredResumeDraft(
            opportunity_id=opportunity.id,
            profile_version=profile.version,
            content=content,
        )
