"""Liveness/version endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from career_agent import __version__

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health() -> dict[str, str]:
    """Confirms the API process is up; carries no store dependency."""
    return {"status": "ok", "version": __version__}
