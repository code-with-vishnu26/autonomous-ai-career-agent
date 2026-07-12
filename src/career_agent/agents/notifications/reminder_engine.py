"""ReminderEngine: reminders computed from real, already-stored data.

Phase 58, ADR-0077.

Three of the brief's seven named reminder types have a real data source
in the current dashboard/API architecture: pending review, pending
submission, and missing promptfoo validation. The other four -- interview
tomorrow/today, incomplete profile, expired API key -- have no real
trigger point (no interview-tracking store the dashboard reads, no
per-user profile endpoint, no API-key-expiry concept anywhere in this
codebase) and are explicitly not built here; see ADR-0077.
"""

from __future__ import annotations

from dataclasses import dataclass

from career_agent.domain.notification import NotificationCategory, NotificationType
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteReviewSessionStore,
    SqliteSubmissionResultStore,
)


@dataclass(frozen=True)
class ReminderCandidate:
    """One reminder ready to be handed to ``NotificationEngine.create``."""

    type: NotificationType
    category: NotificationCategory
    title: str
    message: str


def generate_reminders(
    user_id: str,
    *,
    review_store: SqliteReviewSessionStore,
    application_store: SqliteApplicationSessionStore,
    submission_store: SqliteSubmissionResultStore,
    promptfoo_validated: bool,
) -> list[ReminderCandidate]:
    """Compute every reminder that currently applies to ``user_id``.

    Pure with respect to storage reads only -- performs no writes, no
    delivery, no notification creation. Callers decide whether/how often
    to actually turn a candidate into a persisted, dispatched
    :class:`~career_agent.domain.notification.Notification` (the
    scheduler's reminder job, not this function, owns that cadence).
    """
    candidates: list[ReminderCandidate] = []

    pending_reviews = [
        review
        for review in review_store.by_user(user_id)
        if review.approval_status == "WAITING"
    ]
    if pending_reviews:
        candidates.append(
            ReminderCandidate(
                type="REMINDER",
                category="reminder_pending_review",
                title=f"{len(pending_reviews)} application(s) awaiting review",
                message="You have prepared applications waiting for your decision.",
            )
        )

    approved_session_ids = {
        review.application_session_id
        for review in review_store.by_user(user_id)
        if review.approval_status == "APPROVED"
    }
    submitted_session_ids = {
        result.application_session_id for result in submission_store.by_user(user_id)
    }
    pending_submission_ids = approved_session_ids - submitted_session_ids
    ready_sessions = {
        session.id: session
        for session in application_store.by_user(user_id)
        if session.status == "READY_FOR_REVIEW"
    }
    pending_submission_count = len(pending_submission_ids & ready_sessions.keys())
    if pending_submission_count:
        candidates.append(
            ReminderCandidate(
                type="REMINDER",
                category="reminder_pending_submission",
                title=(
                    f"{pending_submission_count} approved application(s) "
                    "not yet submitted"
                ),
                message=(
                    "You've approved these but haven't run "
                    "`career-agent submit` for them yet."
                ),
            )
        )

    if not promptfoo_validated:
        candidates.append(
            ReminderCandidate(
                type="WARNING",
                category="reminder_promptfoo_validation",
                title="AI features unavailable",
                message=(
                    "No validated promptfoo results found for this "
                    "provider -- tailoring, the truthfulness gate, and "
                    "Career Coach AI features stay blocked until "
                    "`career-agent verify-promptfoo` passes."
                ),
            )
        )

    return candidates
