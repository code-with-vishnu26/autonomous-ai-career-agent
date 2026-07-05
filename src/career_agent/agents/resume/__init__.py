"""Resume Agent (Phase 8).

Tailors a resume for a specific opportunity using only facts present in the user's
master profile (JSON Resume schema). Every output must pass the
fabrication-detection gate before use.

``gate.py`` (Phase 5, ADR-0016) implements the concrete
:class:`~career_agent.core.interfaces.TruthfulnessGate`.

``generator.py`` (Phase 8a, ADR-0022) implements the concrete
:class:`~career_agent.core.interfaces.ResumeGenerator`. `summary` is sourced
read-only from the profile, never LLM-drafted -- the drafter it wraps
(:class:`~career_agent.core.interfaces.ContentDrafter`) structurally cannot
produce one. Routes drafting through a single pinned model this phase, not
yet the general Haiku->Sonnet->Opus cascade (still future work) -- unlike
the gate's `ClaimVerifier`, this port is not permanently cost-cascade-exempt,
since a bad draft is recoverable by the gate downstream.

``pipeline.py`` (Phase 8b, ADR-0023) composes ``generator.py`` and
``gate.py`` into one on-demand call:
:class:`~career_agent.agents.resume.pipeline.ResumeTailoringPipeline`
produces an audited
:class:`~career_agent.domain.models.Application` always, and a
:class:`~career_agent.domain.models.SubmittableApplication` only when
approved. Deliberately stops there -- it never calls
:class:`~career_agent.core.interfaces.Applicator`; tier selection and
obtaining a real
:class:`~career_agent.domain.models.HumanConfirmation` are a separate
slice (Phase 8c, ``agents/apply/pipeline.py``).

For an approved draft, ``ResumeTailoringPipeline.run()`` also computes
``TailoredResume.rendered_text`` via
:func:`~career_agent.domain.rendering.render_tailored_resume` (Phase 8d,
ADR-0025) -- the one place ``draft.content`` and ``profile`` are both
already in scope, so no ``Applicator`` needs a profile dependency just to
render a preview.

``file_renderer.py`` (Phase 9, ADR-0033) renders the real files a company
receives: a deterministic, ATS-safe DOCX (python-docx, zip-timestamp-
normalized -- raw python-docx output is not cross-second deterministic,
verified empirically) and a derived PDF via LibreOffice headless, whose
runtime availability is checked, never assumed
(``PdfConversionUnavailableError`` -- this sandbox shipped ``soffice``
without ``libreoffice-writer``, a real failure mode). Education is
sourced read-only from ``MasterProfile`` and is structurally absent from
every generated type -- the generator cannot override, reorder, or
fabricate it because nothing it produces can carry it (the same shape as
``TailoredWorkEntry`` having no date field). ``ResumeArtifact`` records
(content-hash-addressed filenames: silent overwrite impossible by
construction) land on ``TailoredResume.artifacts`` -- a derived cache
with exactly ``rendered_text``'s status, populated by the pipeline for
approved drafts only, opted into at the composition root via
``artifacts_dir``.

The ATS score gate + auto-retailor loop (Phase 10, ADR-0034) also lives in
``pipeline.py``, opt-in via ``ats_threshold``: tailor -> truthfulness gate
-> deterministic ATS score (:mod:`career_agent.domain.ats_scoring`; the
gate decision is the deterministic score alone, matrix case A1) -> on a
below-threshold result, retailor with a SURFACEABLE-only
``AtsGapReport`` -- a type with no field that could carry a GENUINE
(zero-profile-evidence) gap, so the drafter is structurally never shown a
fabrication target (case B1) -- through the FULL truthfulness gate again
before any re-scoring, every retry, no exceptions (case B3), max 2
retries with identical-draft convergence detection (case B5), ending in
either a pass or the typed, trajectory-carrying
``AtsScoreBelowThresholdError`` (case B4). One render per accepted draft:
the scorer and the human preview consume the literal same
``render_tailored_resume`` string, proven by an ``is``-identity test.
"""
