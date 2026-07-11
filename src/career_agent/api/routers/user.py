"""Per-user profile and Job Search Preferences endpoints (Phase 56, ADR-0074).

``profile`` here means the *account* profile (display name) -- not the
JSON-Resume ``MasterProfile`` (Phase 6), which stays the file-based,
CLI-managed source of truth it has always been. Conflating the two would
misapply "what a dashboard user can edit about their account" to "what is
true about the candidate," the exact distinction ADR-0064 already drew
between ``JobPreferences`` and ``MasterProfile``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from career_agent.api.dependencies import get_user_preferences_store, get_user_store
from career_agent.api.security import get_current_user
from career_agent.domain.job_preferences import JobPreferences
from career_agent.domain.user import User

router = APIRouter(prefix="/user", tags=["user"])


class UpdateProfileRequest(BaseModel):
    """Body for ``PUT /user/profile``."""

    display_name: str | None = None


class ProfileOut(BaseModel):
    """Response for ``PUT /user/profile``."""

    id: str
    email: str
    display_name: str | None


@router.put("/profile", response_model=ProfileOut)
def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    user_store=Depends(get_user_store),
) -> ProfileOut:
    """Update the caller's own display name. Email/password/role are untouched here."""
    user_store.update_profile(current_user.id, display_name=body.display_name)
    return ProfileOut(
        id=current_user.id, email=current_user.email, display_name=body.display_name
    )


@router.get("/preferences", response_model=JobPreferences)
def get_preferences(
    current_user: User = Depends(get_current_user),
    preferences_store=Depends(get_user_preferences_store),
) -> JobPreferences:
    """The caller's stored preferences, or an all-defaults object if never saved."""
    return preferences_store.get(current_user.id) or JobPreferences()


@router.put("/preferences", response_model=JobPreferences)
def update_preferences(
    body: JobPreferences,
    current_user: User = Depends(get_current_user),
    preferences_store=Depends(get_user_preferences_store),
) -> JobPreferences:
    """Replace the caller's stored Job Search Preferences wholesale."""
    preferences_store.save(current_user.id, body)
    return body
