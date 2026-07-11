"""Per-user view of human review decisions (``career-agent review``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from career_agent.api.dependencies import get_review_session_store
from career_agent.api.security import get_current_user
from career_agent.domain.review import ReviewSession
from career_agent.domain.user import User

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("")
def list_reviews(current_user: User = Depends(get_current_user)) -> list[ReviewSession]:
    """Every review decision owned by the caller, newest first."""
    return get_review_session_store().by_user(current_user.id)


@router.get("/pending")
def list_pending_reviews(
    current_user: User = Depends(get_current_user),
) -> list[ReviewSession]:
    """The caller's reviews still ``WAITING`` on a human decision.

    This is the Review Queue page's data source -- filtering already-decided
    reviews out here is presentation logic, not a new decision rule: the
    ``WAITING`` value itself comes from :mod:`career_agent.domain.review`.
    """
    return [
        review
        for review in get_review_session_store().by_user(current_user.id)
        if review.approval_status == "WAITING"
    ]
