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
:class:`~career_agent.domain.models.HumanConfirmation` are a separate,
later slice.
"""
