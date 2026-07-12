"""Human Review Center over HTTP (``career-agent review``, Phase 52/63).

Phase 63 moves this router off the read-only ``/api/`` prefix onto its own
(``/reviews``, mixed GET/POST) -- the same "one feature, one prefix, mixed
methods" shape ``notifications``/``team`` already use -- because it now
carries a real decision-making endpoint (:func:`decide_review`), not just
read views. ``decide_review`` calls the exact same
:class:`~career_agent.agents.review.review_engine.ReviewEngine` the CLI's
``career-agent review`` command uses; only its ``input_fn`` seam changes,
from reading stdin to returning the caller's already-explicit HTTP choice.
No new approval rule is introduced -- ``ReviewEngine`` still owns what
"approved" means.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from career_agent.agents.review.review_engine import ReviewEngine
from career_agent.api.dependencies import (
    get_application_session_store,
    get_review_session_store,
)
from career_agent.api.security import get_current_user
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.review import ReviewSession, build_review_session
from career_agent.domain.user import User

router = APIRouter(prefix="/reviews", tags=["reviews"])


class DecideReviewRequest(BaseModel):
    """Body for ``POST /reviews/decide``."""

    application_session_id: str
    approved: bool
    notes: str | None = None


@router.get("", response_model=list[ReviewSession])
def list_reviews(
    current_user: User = Depends(get_current_user),
    review_session_store=Depends(get_review_session_store),
) -> list[ReviewSession]:
    """Every review decision owned by the caller, newest first."""
    return review_session_store.by_user(current_user.id)


@router.get("/pending", response_model=list[ApplicationSession])
def list_pending_reviews(
    current_user: User = Depends(get_current_user),
    application_session_store=Depends(get_application_session_store),
    review_session_store=Depends(get_review_session_store),
) -> list[ApplicationSession]:
    """The caller's ``READY_FOR_REVIEW`` sessions with no decision recorded yet.

    Phase 63 fix: ``ReviewSession.approval_status`` can never actually be
    ``"WAITING"`` in this codebase -- ``ReviewEngine.review()`` only ever
    returns APPROVED/REJECTED/CANCELLED/TIMEOUT (see its own docstring) --
    so this endpoint's original Phase 52 behavior (filtering
    ``ReviewSession``s on ``approval_status == "WAITING"``) always returned
    an empty list. "Pending" is redefined to what it actually means: a
    prepared ``ApplicationSession`` ready for a human decision that has not
    yet received one -- returning the session itself, since no
    ``ReviewSession`` exists for it yet by definition.
    """
    reviewed_ids = {
        review.application_session_id
        for review in review_session_store.by_user(current_user.id)
    }
    return [
        session
        for session in application_session_store.by_user(current_user.id)
        if session.status == "READY_FOR_REVIEW" and session.id not in reviewed_ids
    ]


@router.post("/decide", response_model=ReviewSession)
def decide_review(
    body: DecideReviewRequest,
    current_user: User = Depends(get_current_user),
    application_session_store=Depends(get_application_session_store),
    review_session_store=Depends(get_review_session_store),
) -> ReviewSession:
    """The sole web-reachable ``READY_FOR_REVIEW`` -> APPROVED/REJECTED transition.

    Exactly the same safety as the CLI: one decision per session
    (``review_sessions`` is append-only, and this route refuses a second
    decision for the same session rather than silently recording another
    one), and only an explicit ``approved=True`` produces ``APPROVED`` --
    ``ReviewEngine`` itself still enforces that, this route cannot bypass it.
    """
    session = next(
        (
            candidate
            for candidate in application_session_store.by_user(current_user.id)
            if candidate.id == body.application_session_id
        ),
        None,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application session not found.",
        )
    if session.status != "READY_FOR_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session status is {session.status!r}, not READY_FOR_REVIEW.",
        )
    already_reviewed = any(
        review.application_session_id == session.id
        for review in review_session_store.by_user(current_user.id)
    )
    if already_reviewed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This session already has a recorded review decision.",
        )

    answer = "y" if body.approved else "n"
    result = ReviewEngine().review(
        session,
        input_fn=lambda _prompt: answer,
        notes=body.notes,
        print_fn=lambda _line: None,
    )
    review = build_review_session(str(uuid.uuid4()), session, result)
    review_session_store.save(review, user_id=current_user.id)
    return review
