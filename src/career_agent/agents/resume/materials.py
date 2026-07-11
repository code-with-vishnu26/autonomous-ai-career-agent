"""Compose variant selection + tailoring + cover letter into one call (ADR-0068).

Phase 50's goal, verbatim: Job Found -> Extract Job Description -> Analyze
Required Skills -> Compare Against Master Profile -> Generate Tailored
Resume -> Generate Tailored Cover Letter -> Store Resume Variant -> Return
Artifact to Browser Layer. Nothing here submits anything.

This module is a thin composition layer over three already-independent
pieces, and deliberately touches zero lines of any of them:

- :class:`~career_agent.agents.resume.pipeline.ResumeTailoringPipeline` --
  unmodified. It alone still owns generate -> truthfulness-gate ->
  ATS-gate -> render/persist; this module never reimplements or bypasses
  any part of that.
- :func:`~career_agent.domain.resume_variants.select_closest_variant` --
  purely advisory: it only ever *ranks* previously approved variants for
  logging/inspection. The pipeline runs unconditionally regardless of its
  answer -- reusing a close variant as a generation shortcut is explicitly
  *not* built here, so there is no path by which an advisory ranking could
  ever influence what gets gated.
- :func:`~career_agent.domain.cover_letter.assemble_cover_letter` -- runs
  only after the pipeline's ``truthfulness.approved`` is ``True``, and only
  on the resume it approved.

**No storage dependency, on purpose.** ``ResumeTailoringPipeline`` never
touches ``storage/`` either -- ``cli.py`` calls ``application_store.record()``
itself, at the composition root, after ``pipeline.run()`` returns. This
module mirrors that exact convention for the new
``SqliteResumeVariantStore``: ``build_materials()`` returns a built-but-unsaved
:class:`~career_agent.domain.resume_variants.ResumeVariant` (Phase 50's
"Store Resume Variant" step's *data*), and the caller decides whether/how to
persist it, the same as every other store in this project.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import NamedTuple

from career_agent.agents.resume.pipeline import (
    ResumeTailoringPipeline,
    ResumeTailoringResult,
)
from career_agent.domain.cover_letter import TailoredCoverLetter, assemble_cover_letter
from career_agent.domain.models import MasterProfile, Opportunity
from career_agent.domain.resume_variants import ResumeVariant, select_closest_variant


class ApplicationMaterials(NamedTuple):
    """Everything Phase 50 produces for one opportunity.

    Ready for the browser layer to hand to a human for review; nothing here
    is submitted. ``new_variant`` is populated only when the pipeline
    approved the resume -- a rejected draft is never memorized as a
    reusable variant -- and is not yet persisted (see module docstring).
    """

    tailoring: ResumeTailoringResult
    cover_letter: TailoredCoverLetter | None
    closest_prior_variant: ResumeVariant | None
    new_variant: ResumeVariant | None


class ResumeVariantEngine:
    """Runs the full Phase 50 workflow for one opportunity."""

    def __init__(self, pipeline: ResumeTailoringPipeline) -> None:
        """Wrap an unmodified :class:`ResumeTailoringPipeline` (ADR-0068)."""
        self._pipeline = pipeline

    async def build_materials(
        self,
        opportunity: Opportunity,
        profile: MasterProfile,
        *,
        category: str,
        prior_variants: list[ResumeVariant] | None = None,
    ) -> ApplicationMaterials:
        """Tailor, gate, assemble a cover letter, and build a new variant.

        ``category`` is a free-form label the caller chooses for this
        opportunity (e.g. from the search that found it) -- carried onto
        the built ``ResumeVariant`` so a caller can group/query stored
        variants later; it never influences the pipeline's own gated
        output. ``prior_variants`` (already-persisted variants in this
        category, fetched by the caller) is only ever consulted for the
        advisory ``closest_prior_variant`` comparison.
        """
        closest_prior_variant = select_closest_variant(
            prior_variants or [], opportunity.description_raw
        )

        tailoring = await self._pipeline.run(opportunity, profile)

        if not tailoring.application.resume.truthfulness.approved:
            return ApplicationMaterials(
                tailoring=tailoring,
                cover_letter=None,
                closest_prior_variant=closest_prior_variant,
                new_variant=None,
            )

        resume = tailoring.application.resume
        cover_letter = assemble_cover_letter(
            resume.content,
            opportunity,
            profile_version=resume.profile_version,
            applicant_name=profile.basics.name,
        )
        new_variant = ResumeVariant(
            id=str(uuid.uuid4()),
            category=category,
            profile_version=resume.profile_version,
            content=resume.content,
            created_at=datetime.now(UTC).isoformat(),
        )

        return ApplicationMaterials(
            tailoring=tailoring,
            cover_letter=cover_letter,
            closest_prior_variant=closest_prior_variant,
            new_variant=new_variant,
        )
