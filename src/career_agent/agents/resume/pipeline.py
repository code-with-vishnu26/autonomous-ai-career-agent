"""Compose generate -> gate -> submittable into one on-demand path (ADR-0023).

The first slice where a real ``Opportunity`` can flow all the way from
tailoring through gating into a submittable application. Deliberately stops
there: it does **not** call ``Applicator.prepare()``/``submit()``. Producing
a :class:`~career_agent.domain.models.SubmittableApplication` is pure data
assembly (no network I/O, no human confirmation needed); actually invoking a
tier is a categorically different action requiring tier selection and a real
:class:`~career_agent.domain.models.HumanConfirmation` -- a further,
separable step, the same sequencing logic as 7a proving safety machinery
before 7b3 added a new tier.

On-demand only: this pipeline runs once per call, given an explicit
``Opportunity``/``MasterProfile`` pair. It does not scan, schedule, or
select opportunities on its own -- the profile-staleness and
send-confirmation gaps (ADR-0018/ADR-0021) stay correctly deferred; nothing
here trips their "before any scheduled/autonomous run" trigger.

``TailoredResume.rendered_text`` (ADR-0025) is computed here, once, only
for an *approved* draft -- the one place both ``draft.content`` and
``profile`` are in scope at resume-creation time, so no ``Applicator``
needs its own profile dependency to render a preview later. A rejected
draft's ``rendered_text`` stays ``None``: rendering could itself raise
(``render_tailored_resume`` independently re-verifies every
``source_entry_id``, the same discipline the gate already applied), and a
rejected resume was never going to be submitted, so there is nothing to
render it for.

``Application.applicant`` (ADR-0027) is likewise snapshotted here from
``profile.basics``, frozen at construction time rather than resolved live
by a submission tier later -- the same drift this pipeline already prevents
for resume content (``profile_version``), now extended to identity.
``Application.legal_status`` (ADR-0032) is snapshotted here the same way,
from ``profile.legal_status`` -- one field wider on the same precedent, so
``BrowserApplicator`` can auto-answer a captured legal-status fact without
ever depending on ``MasterProfile`` storage itself.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import NamedTuple

from career_agent.agents.resume.file_renderer import (
    PdfConversionUnavailableError,
    convert_to_pdf,
    render_resume_docx,
)
from career_agent.core.bus import EventBus
from career_agent.core.events import ResumeTailored, TruthfulnessRejected
from career_agent.core.interfaces import ResumeGenerator, TruthfulnessGate
from career_agent.domain.models import (
    Application,
    MasterProfile,
    Opportunity,
    ResumeArtifact,
    SubmittableApplication,
    TailoredContent,
    TailoredResume,
    to_submittable,
)
from career_agent.domain.rendering import render_tailored_resume

logger = logging.getLogger(__name__)


class ResumeTailoringResult(NamedTuple):
    """The pipeline's output.

    Always an audited ``Application``, plus a :class:`SubmittableApplication`
    only when the gate approved.
    """

    application: Application
    submittable: SubmittableApplication | None


class ResumeTailoringPipeline:
    """Generator -> gate -> Application/SubmittableApplication, one call at a time."""

    def __init__(
        self,
        generator: ResumeGenerator,
        gate: TruthfulnessGate,
        bus: EventBus,
        *,
        artifacts_dir: Path | None = None,
    ) -> None:
        """Configure the pipeline with a generator, a gate, and the event bus.

        ``bus`` is used only to *notify* (``ResumeTailored``/
        ``TruthfulnessRejected``) -- events never gate behavior here, same
        as everywhere else in this project (ADR-0005 amendment).

        ``artifacts_dir`` (Phase 9, ADR-0033): where real DOCX/PDF resume
        files are written for approved drafts. ``None`` means no files are
        generated -- file generation is opted into at the composition root
        (``cli.py`` passes ``Settings.artifacts_dir``), so callers that only
        need the in-memory result (most tests, any future scoring-only
        flow) never touch the filesystem.
        """
        self._generator = generator
        self._gate = gate
        self._bus = bus
        self._artifacts_dir = artifacts_dir

    async def run(
        self, opportunity: Opportunity, profile: MasterProfile
    ) -> ResumeTailoringResult:
        """Tailor and gate a resume for ``opportunity``.

        Raises whatever the generator or gate raise (e.g.
        ``MissingSummaryError`` from an incomplete profile) -- this is
        composition, not a resilience layer; it does not swallow or paper
        over a precondition failure the human needs to fix.
        """
        draft = await self._generator.tailor(opportunity, profile)
        truthfulness = await self._gate.verify(draft, profile)

        rendered_text = (
            render_tailored_resume(draft.content, profile)
            if truthfulness.approved
            else None
        )
        resume_id = str(uuid.uuid4())
        artifacts = (
            self._render_artifacts(resume_id, draft.content, profile)
            if truthfulness.approved and self._artifacts_dir is not None
            else []
        )
        resume = TailoredResume(
            id=resume_id,
            opportunity_id=opportunity.id,
            profile_version=profile.version,
            content=draft.content,
            rendered_text=rendered_text,
            artifacts=artifacts,
            truthfulness=truthfulness,
        )
        application = Application(
            id=str(uuid.uuid4()),
            opportunity_id=opportunity.id,
            resume=resume,
            applicant=profile.basics,
            legal_status=profile.legal_status,
            status="pending" if truthfulness.approved else "rejected",
        )

        if truthfulness.approved:
            await self._bus.publish(
                ResumeTailored(
                    correlation_id=opportunity.id,
                    opportunity_id=opportunity.id,
                    resume_id=resume.id,
                )
            )
            return ResumeTailoringResult(
                application=application, submittable=to_submittable(application)
            )

        await self._bus.publish(
            TruthfulnessRejected(
                correlation_id=opportunity.id,
                opportunity_id=opportunity.id,
                rejection_count=len(truthfulness.rejections),
            )
        )
        return ResumeTailoringResult(application=application, submittable=None)

    def _render_artifacts(
        self, resume_id: str, content: TailoredContent, profile: MasterProfile
    ) -> list[ResumeArtifact]:
        """Render the DOCX (always) and PDF (environment-permitting) files.

        A missing/failing PDF converter is not a content problem and does
        not fail the run: the DOCX -- the canonical, deterministic artifact
        and the format Lever's upload accepts -- is already on disk. The
        absence is structurally visible (no ``format="pdf"`` entry in the
        returned list), not swallowed into a boolean nobody checks; direct
        callers of :func:`convert_to_pdf` still get the typed error.
        """
        assert self._artifacts_dir is not None  # guarded by caller
        docx_artifact = render_resume_docx(
            resume_id, content, profile, self._artifacts_dir
        )
        artifacts = [docx_artifact]
        try:
            artifacts.append(
                convert_to_pdf(docx_artifact, self._artifacts_dir)
            )
        except PdfConversionUnavailableError as exc:
            logger.warning("PDF view not produced: %s", exc)
        return artifacts
