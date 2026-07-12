"""DigestGenerator: daily/weekly/monthly summaries from real counts.

Phase 58, ADR-0077.

The brief's own example digest ("12 new jobs, 4 prepared, 2 awaiting
review, 1 submitted, 1 interview scheduled") names two metrics with no
real data source in the current dashboard/API architecture: "new jobs"
(discovery is a CLI-only pipeline never exposed to the dashboard) and
"interview scheduled" (no interview-tracking store exists anywhere the
dashboard reads). Both are omitted here, not fabricated as zero or
guessed -- the digest reports exactly the three counts this phase can
compute for real: prepared, awaiting review, submitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
)

DigestPeriod = Literal["daily", "weekly", "monthly"]

_PERIOD_WINDOW = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}


@dataclass(frozen=True)
class DigestSummary:
    """Real counts for one user over one period -- the digest's raw material."""

    period: DigestPeriod
    prepared: int
    awaiting_review: int
    submitted: int

    def as_lines(self) -> list[str]:
        """Plain-text lines, in the brief's own "N noun" style."""
        return [
            f"{self.prepared} application(s) prepared",
            f"{self.awaiting_review} awaiting review",
            f"{self.submitted} submitted",
        ]


def generate_digest(
    user_id: str,
    period: DigestPeriod,
    *,
    application_store: SqliteApplicationSessionStore,
    review_store: SqliteReviewSessionStore,
    submission_store: SqliteSubmissionResultStore,
    now: datetime,
) -> DigestSummary:
    """Compute ``period``'s real counts for ``user_id`` as of ``now``."""
    window_start = now - _PERIOD_WINDOW[period]

    prepared = sum(
        1
        for session in application_store.by_user(user_id)
        if session.created_at >= window_start
    )
    awaiting_review = sum(
        1
        for review in review_store.by_user(user_id)
        if review.approval_status == "WAITING"
    )
    submitted = sum(
        1
        for result in submission_store.by_user(user_id)
        if result.submitted_at is not None and result.submitted_at >= window_start
    )
    return DigestSummary(
        period=period,
        prepared=prepared,
        awaiting_review=awaiting_review,
        submitted=submitted,
    )
