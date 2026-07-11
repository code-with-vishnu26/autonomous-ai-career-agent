"""Per-user view of stored résumé variants (``career-agent prepare``, ADR-0068)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from career_agent.api.dependencies import get_resume_variant_store
from career_agent.api.security import get_current_user
from career_agent.domain.resume_variants import ResumeVariant
from career_agent.domain.user import User

router = APIRouter(prefix="/api/resume-variants", tags=["resume-variants"])


@router.get("")
def list_resume_variants(
    current_user: User = Depends(get_current_user),
) -> list[ResumeVariant]:
    """Every résumé variant owned by the caller, most recent first."""
    return get_resume_variant_store().by_user(current_user.id)
