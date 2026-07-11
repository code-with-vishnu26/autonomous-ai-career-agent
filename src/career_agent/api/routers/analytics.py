"""Aggregate counts across the caller's own data -- no new metrics engine.

Every number here is a plain ``collections.Counter`` over rows the stores
already return for the authenticated caller; there is no separate
analytics computation living anywhere else in the codebase for this to
duplicate (the CLI's ``career-agent report``/funnel report reads from the
older ``SqliteApplicationStore``, a different, pre-existing pipeline --
this route intentionally does not touch it, to avoid conflating the two
application pipelines Phases 51-53's ADRs already documented as a
deliberate separation).
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from career_agent.api.dependencies import (
    get_application_session_store,
    get_review_session_store,
    get_submission_result_store,
)
from career_agent.api.security import get_current_user
from career_agent.domain.user import User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class AnalyticsSummary(BaseModel):
    """Counts by status, one dict per store."""

    applications_by_status: dict[str, int]
    reviews_by_status: dict[str, int]
    submissions_by_status: dict[str, int]


@router.get("/summary")
def analytics_summary(
    current_user: User = Depends(get_current_user),
) -> AnalyticsSummary:
    """Point-in-time status breakdown across the caller's own data."""
    applications = get_application_session_store().by_user(current_user.id)
    reviews = get_review_session_store().by_user(current_user.id)
    submissions = get_submission_result_store().by_user(current_user.id)
    return AnalyticsSummary(
        applications_by_status=dict(Counter(a.status for a in applications)),
        reviews_by_status=dict(Counter(r.approval_status for r in reviews)),
        submissions_by_status=dict(Counter(s.status for s in submissions)),
    )
