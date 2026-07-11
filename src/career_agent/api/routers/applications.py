"""Read-only view of prepared application sessions (``career-agent prepare``)."""

from __future__ import annotations

from fastapi import APIRouter

from career_agent.api.dependencies import get_application_session_store
from career_agent.domain.application_session import ApplicationSession

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("")
def list_applications() -> list[ApplicationSession]:
    """Every prepared application session, newest first."""
    return get_application_session_store().all_sessions()
