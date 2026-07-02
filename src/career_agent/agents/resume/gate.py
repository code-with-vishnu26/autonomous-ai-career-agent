"""The concrete, LLM-backed :class:`TruthfulnessGate` (ADR-0016).

Implements the Phase 2 ``TruthfulnessGate`` Protocol (``core/interfaces.py``,
unchanged by this phase) using an injected :class:`ClaimVerifier`. This is the
orchestration layer: it decides *what* evidence a claim is checked against and
*how* verdicts are aggregated; the verifier decides *whether* a given claim is
entailed by that evidence.

Design commitments (ADR-0016):

- **Entailment over keyword matching.** Every work/project highlight is judged
  holistically against the *union* of evidence reachable from its linked
  profile entry (that entry's own highlights, plus the full skills list, plus
  all projects) -- never checked field-by-field against isolated lookups. This
  is what makes a composite fabrication (a real skill + a real achievement
  stitched into an invented combined claim) fail because the added detail is
  genuinely ungrounded, not because some unrelated fragment happens to trip an
  unrelated rule.
- **Skills-list membership is structural, not judged.** A claimed skill is
  checked by normalized presence in ``profile.skills`` -- deterministic, no
  model call, no ambiguity to adjudicate.
- **Dates are structurally impossible to fabricate in this channel.**
  ``TailoredWorkEntry`` carries no date fields (Phase 2's domain model), so a
  tailored entry cannot independently assert dates -- they are always the
  linked profile entry's own, by construction. This is a *stronger* guarantee
  than a behavioral check: date fabrication in structured content isn't caught
  by the gate, it's impossible to construct in the first place.
- **``summary`` (free text) is explicitly out of scope this phase**, not
  silently skipped -- see ADR-0016's named-gap note and its coupling to Phase
  8's ``ResumeGenerator`` design.
- **Sub-threshold confidence overrides a "verified" verdict to blocked.** A
  verifier saying "verified" without enough confidence is not trusted more
  than one that says "not verified."
- **Any verifier failure is an explicit, tested block** -- never a silent pass
  and never an uncaught exception propagating out of ``verify()``.
"""

from __future__ import annotations

from career_agent.core.interfaces import ClaimVerifier
from career_agent.domain.models import (
    EvidenceRef,
    MasterProfile,
    ProjectEntry,
    RejectionReason,
    Statement,
    TailoredResumeDraft,
    TruthfulnessResult,
    WorkEntry,
)

_DEFAULT_CONFIDENCE_THRESHOLD = 0.7


class LLMTruthfulnessGate:
    """The concrete truthfulness gate, backed by an injected :class:`ClaimVerifier`."""

    def __init__(
        self,
        verifier: ClaimVerifier,
        *,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        """Configure the gate with a verifier and the minimum confidence to trust it."""
        self._verifier = verifier
        self._threshold = confidence_threshold

    async def verify(
        self, draft: TailoredResumeDraft, profile: MasterProfile
    ) -> TruthfulnessResult:
        """Verify every checkable statement in ``draft`` against ``profile``."""
        statements: list[Statement] = []
        rejections: list[RejectionReason] = []

        for skill in draft.content.skills:
            statement, rejection = self._check_skill(skill, profile)
            statements.append(statement)
            if rejection is not None:
                rejections.append(rejection)

        for work_entry in draft.content.work:
            source = _find_work_entry(profile, work_entry.source_entry_id)
            if source is None:
                statement, rejection = _missing_entry(
                    f"worked as {work_entry.position}", work_entry.source_entry_id
                )
                statements.append(statement)
                rejections.append(rejection)
                continue
            evidence = _work_evidence(source, profile)
            statement, rejection = await self._check_claim(
                work_entry.position, evidence, profile.version, "work", source.id
            )
            statements.append(statement)
            if rejection is not None:
                rejections.append(rejection)
            for highlight in work_entry.highlights:
                statement, rejection = await self._check_claim(
                    highlight, evidence, profile.version, "work", source.id
                )
                statements.append(statement)
                if rejection is not None:
                    rejections.append(rejection)

        for project_entry in draft.content.projects:
            source_proj = _find_project_entry(profile, project_entry.source_entry_id)
            if source_proj is None:
                statement, rejection = _missing_entry(
                    project_entry.name, project_entry.source_entry_id
                )
                statements.append(statement)
                rejections.append(rejection)
                continue
            evidence = _project_evidence(source_proj, profile)
            for highlight in project_entry.highlights:
                statement, rejection = await self._check_claim(
                    highlight, evidence, profile.version, "projects", source_proj.id
                )
                statements.append(statement)
                if rejection is not None:
                    rejections.append(rejection)

        approved = all(statement.verified for statement in statements)
        return TruthfulnessResult(
            profile_version=profile.version,
            approved=approved,
            statements=statements,
            rejections=rejections,
            prompt_version=self._verifier.prompt_version,
        )

    def _check_skill(
        self, skill: str, profile: MasterProfile
    ) -> tuple[Statement, RejectionReason | None]:
        """Check skill-list membership structurally -- no model call."""
        match = _normalize(skill)
        for entry in profile.skills:
            if _normalize(entry.name) == match:
                evidence = EvidenceRef(
                    profile_version=profile.version,
                    section="skills",
                    entry_id=entry.id,
                    field="name",
                    excerpt=entry.name,
                )
                return (
                    Statement(
                        text=skill, evidence=evidence, confidence=1.0, verified=True
                    ),
                    None,
                )
        statement = Statement(text=skill, evidence=None, confidence=0.0, verified=False)
        rejection = RejectionReason(
            statement_text=skill,
            category="skill_not_found",
            detail=f'skill "{skill}" not found in master profile',
        )
        return statement, rejection

    async def _check_claim(
        self,
        claim_text: str,
        evidence: str,
        profile_version: str,
        section: str,
        entry_id: str,
    ) -> tuple[Statement, RejectionReason | None]:
        """Check one free-text claim against evidence via the injected verifier.

        Any verifier exception is caught here and turned into an explicit
        block -- infrastructure failure is never evidence of truthfulness.
        """
        try:
            verdict = await self._verifier.verify_claim(claim_text, evidence)
        except Exception as exc:  # noqa: BLE001 -- fail closed, never propagate
            statement = Statement(
                text=claim_text, evidence=None, confidence=0.0, verified=False
            )
            rejection = RejectionReason(
                statement_text=claim_text,
                category="verification_failed",
                detail=f"claim verifier failed: {exc}",
            )
            return statement, rejection

        # Sub-threshold confidence overrides "verified" -- a low-confidence
        # "yes" is not trusted more than a "no".
        trusted = verdict.verified and verdict.confidence >= self._threshold
        if trusted:
            # index is set only when the verifier names one clear source
            # highlight; left None when the claim honestly synthesizes
            # multiple facts (the excerpt then carries the combined evidence).
            evidence_ref = EvidenceRef(
                profile_version=profile_version,
                section=section,  # type: ignore[arg-type]
                entry_id=entry_id,
                field="highlights",
                index=verdict.matched_index,
                excerpt=evidence[:280],
            )
            statement = Statement(
                text=claim_text,
                evidence=evidence_ref,
                confidence=verdict.confidence,
                verified=True,
            )
            return statement, None

        statement = Statement(
            text=claim_text,
            evidence=None,
            confidence=verdict.confidence,
            verified=False,
        )
        category = verdict.category or "evidence_missing"
        detail = verdict.detail or (
            f"verifier confidence {verdict.confidence:.2f} below threshold "
            f"{self._threshold:.2f}"
        )
        rejection = RejectionReason(
            statement_text=claim_text, category=category, detail=detail
        )
        return statement, rejection


def _missing_entry(
    label: str, source_entry_id: str
) -> tuple[Statement, RejectionReason]:
    statement = Statement(text=label, evidence=None, confidence=0.0, verified=False)
    rejection = RejectionReason(
        statement_text=label,
        category="employer_mismatch",
        detail=f"referenced entry {source_entry_id!r} not found in master profile",
    )
    return statement, rejection


def _find_work_entry(profile: MasterProfile, entry_id: str) -> WorkEntry | None:
    return next((entry for entry in profile.work if entry.id == entry_id), None)


def _find_project_entry(profile: MasterProfile, entry_id: str) -> ProjectEntry | None:
    return next((entry for entry in profile.projects if entry.id == entry_id), None)


def _work_evidence(entry: WorkEntry, profile: MasterProfile) -> str:
    """Assemble the evidence union reachable from one work entry.

    Includes the entry's own position/highlights AND the full skills list and
    all projects, so a claim can be judged against everything the profile
    vouches for -- never just the isolated field being checked. This is what
    lets the verifier catch a composite claim (a real skill and a real
    achievement stitched into an invented combined claim) as genuinely
    ungrounded, rather than passing because some fragment matches elsewhere.
    """
    lines = [f"Position: {entry.position}"]
    lines.extend(f"- {highlight}" for highlight in entry.highlights)
    lines.append("Skills: " + ", ".join(skill.name for skill in profile.skills))
    for project in profile.projects:
        lines.append(f"Project ({project.name}): " + "; ".join(project.highlights))
    return "\n".join(lines)


def _project_evidence(entry: ProjectEntry, profile: MasterProfile) -> str:
    lines = [f"Project: {entry.name}"]
    lines.extend(f"- {highlight}" for highlight in entry.highlights)
    lines.append("Skills: " + ", ".join(skill.name for skill in profile.skills))
    return "\n".join(lines)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
