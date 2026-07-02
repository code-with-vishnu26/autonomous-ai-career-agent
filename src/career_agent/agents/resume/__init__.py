"""Resume Agent (Phase 7).

Tailors a resume for a specific opportunity using only facts present in the user's
master profile (JSON Resume schema). Routes generation through the Claude cost
cascade. Every output must pass the fabrication-detection gate before use.

``gate.py`` (Phase 5, ADR-0016) implements the concrete
:class:`~career_agent.core.interfaces.TruthfulnessGate`. The generator
(``ResumeGenerator``) that produces drafts for the gate to check is still
Phase 7 work -- Phase 5 built and validated the gate against directly-
constructed :class:`~career_agent.domain.models.TailoredResumeDraft` fixtures,
deliberately without a generator to build against.
"""
