"""Per-user view of submission attempts (``career-agent submit``, ADR-0071)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from career_agent.api.dependencies import get_submission_result_store
from career_agent.api.security import get_current_user
from career_agent.domain.submission import SubmissionResult
from career_agent.domain.user import User

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


@router.get("")
def list_submissions(
    current_user: User = Depends(get_current_user),
) -> list[SubmissionResult]:
    """Every submission attempt owned by the caller, newest first.

    Read-only: this route cannot cause a submission. Triggering one remains
    exclusively a ``career-agent submit`` CLI action, so the human-in-the-loop
    countdown/confirmation gate ADR-0071 built stays the only path to a real
    click, unmoved by this phase.
    """
    return get_submission_result_store().by_user(current_user.id)
