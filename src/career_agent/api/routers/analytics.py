"""Aggregate counts across the existing stores -- no new metrics engine.

Every number here is a plain ``collections.Counter`` over rows the stores
already return; there is no separate analytics computation living anywhere
else in the codebase for this to duplicate (the CLI's ``career-agent
report``/funnel report reads from the older ``SqliteApplicationStore``,
a different, pre-existing pipeline -- this route intentionally does not
touch it, to avoid conflating the two application pipelines Phases 51-53's
ADRs already documented as a deliberate separation).
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter
from pydantic import BaseModel

from career_agent.api.dependencies import (
    get_application_session_store,
    get_review_session_store,
    get_submission_result_store,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class AnalyticsSummary(BaseModel):
    """Counts by status, one dict per store."""

    applications_by_status: dict[str, int]
    reviews_by_status: dict[str, int]
    submissions_by_status: dict[str, int]


@router.get("/summary")
def analytics_summary() -> AnalyticsSummary:
    """Point-in-time status breakdown across applications/reviews/submissions."""
    applications = get_application_session_store().all_sessions()
    reviews = get_review_session_store().all_reviews()
    submissions = get_submission_result_store().all_results()
    return AnalyticsSummary(
        applications_by_status=dict(Counter(a.status for a in applications)),
        reviews_by_status=dict(Counter(r.approval_status for r in reviews)),
        submissions_by_status=dict(Counter(s.status for s in submissions)),
    )
