"""Read-only view of human review decisions (``career-agent review``)."""

from __future__ import annotations

from fastapi import APIRouter

from career_agent.api.dependencies import get_review_session_store
from career_agent.domain.review import ReviewSession

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("")
def list_reviews() -> list[ReviewSession]:
    """Every recorded review decision, newest first."""
    return get_review_session_store().all_reviews()


@router.get("/pending")
def list_pending_reviews() -> list[ReviewSession]:
    """Reviews still awaiting a human decision (``approval_status == "WAITING"``).

    This is the Review Queue page's data source -- filtering already-decided
    reviews out here is presentation logic, not a new decision rule: the
    ``WAITING`` value itself comes from :mod:`career_agent.domain.review`.
    """
    return [
        review
        for review in get_review_session_store().all_reviews()
        if review.approval_status == "WAITING"
    ]
