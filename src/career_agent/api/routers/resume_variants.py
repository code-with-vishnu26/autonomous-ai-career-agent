"""Read-only view of stored résumé variants (``career-agent prepare``, ADR-0068)."""

from __future__ import annotations

from fastapi import APIRouter

from career_agent.api.dependencies import get_resume_variant_store
from career_agent.domain.resume_variants import ResumeVariant

router = APIRouter(prefix="/api/resume-variants", tags=["resume-variants"])


@router.get("")
def list_resume_variants() -> list[ResumeVariant]:
    """Every stored résumé variant, most recently created database row first."""
    return get_resume_variant_store().all_variants()
