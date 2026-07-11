"""Per-user view of prepared application sessions (``career-agent prepare``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from career_agent.api.dependencies import get_application_session_store
from career_agent.api.security import get_current_user
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.user import User

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("")
def list_applications(
    current_user: User = Depends(get_current_user),
) -> list[ApplicationSession]:
    """Every application session owned by the caller, newest first."""
    return get_application_session_store().by_user(current_user.id)
