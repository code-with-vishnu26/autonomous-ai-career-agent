"""Human Review Center: the sole APPROVED-transition boundary (Phase 52, ADR-0070).

Phase 51's `ApplicationSession` already stops before any submit click and
already carries everything a human needs to decide: which fields were
filled, what was uploaded, what's still missing, and every warning. This
module adds nothing to *that* data -- it adds the **decision** layered on
top of it.

``ReviewSession`` deliberately does **not** duplicate `ApplicationSession`'s
content (résumé variant, cover letter body, filled/missing fields,
warnings, uploaded files). It stores a link (`application_session_id`) plus
a few cheap, denormalized display fields -- the same "denormalize identity/
display fields, not full content" precedent
`~career_agent.storage.sqlite.SqliteApplicationStore` already established
for its own `company`/`title` columns. The full detail a human reviewed is
always re-derived from the referenced `ApplicationSession`, never copied,
so there is exactly one place that content can ever drift from -- the
`ApplicationSession` itself.

``format_review_summary`` is pure, deterministic text formatting -- no LLM
call, no judgment, no filtering. It shows every warning and every missing
field; nothing is ever hidden from the human making the approval decision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .application_session import ApplicationSession

#: - ``WAITING``: a review has been started but no decision recorded yet.
#: - ``APPROVED``: the human explicitly said yes. The *only* state a
#:   Submission Engine (Phase 53) may ever act on.
#: - ``REJECTED``: the human explicitly said no.
#: - ``CANCELLED``: the human interrupted the review (e.g. Ctrl+C) without
#:   answering either way.
#: - ``TIMEOUT``: no answer was given within a bounded wait.
ApprovalStatus = Literal["WAITING", "APPROVED", "REJECTED", "CANCELLED", "TIMEOUT"]


class ReviewSession(BaseModel):
    """One human review decision for one prepared, unsubmitted application."""

    id: str
    application_session_id: str
    company: str
    job_title: str
    provider: str
    approval_status: ApprovalStatus
    review_notes: str | None = None
    created_at: datetime
    approved_at: datetime | None = None


class ReviewResult(BaseModel):
    """What a single review call decided -- returned to the caller directly.

    ``next_action`` is a plain, informational string, not a dispatch
    instruction any code branches on -- ``"eligible_for_submission_engine"``
    only ever means "a future Phase 53 may now inspect this," never that
    anything here calls one. No Submission Engine exists in this codebase
    yet.
    """

    approved: bool
    status: ApprovalStatus
    notes: str | None = None
    review_time: datetime
    next_action: Literal[
        "eligible_for_submission_engine", "revise_and_re_prepare", "none"
    ]


def format_review_summary(session: ApplicationSession) -> str:
    """A deterministic, human-readable summary of ``session``. No AI, no judgment.

    Every warning and every missing field is always shown -- this function
    has no filtering/prioritization logic that could hide something from
    the reviewer.
    """
    lines = [
        "=" * 33,
        "Application Review",
        "=" * 33,
        "",
        "Company",
        f"  {session.company}",
        "",
        "Role",
        f"  {session.job_title}",
        "",
        "Provider",
        f"  {session.provider}",
        "",
    ]

    if session.uploaded_files or session.cover_letter_body is not None:
        lines.append("Uploaded")
        if session.uploaded_files:
            lines.append("  resume")
            for path in session.uploaded_files:
                lines.append(f"    {path}")
        if session.cover_letter_body is not None:
            lines.append("  cover letter (attach manually -- see warnings)")
        lines.append("")

    if session.filled_fields:
        lines.append("Filled")
        lines.extend(f"  {field}" for field in session.filled_fields)
        lines.append("")

    if session.warnings:
        lines.append("Warnings")
        lines.extend(f"  {warning}" for warning in session.warnings)
        lines.append("")

    if session.missing_fields:
        lines.append("Missing")
        lines.extend(f"  {field}" for field in session.missing_fields)
        lines.append("")

    lines.append("Ready")
    lines.append(f"  {'YES' if session.status == 'READY_FOR_REVIEW' else 'NO'}")

    return "\n".join(lines).rstrip() + "\n"


def build_review_session(
    review_id: str,
    application_session: ApplicationSession,
    result: ReviewResult,
) -> ReviewSession:
    """Assemble the record a caller persists for one review decision.

    Pure construction, no I/O -- the caller (composition root) decides
    whether/how to store it, the same "engine returns data, caller
    persists" shape ``ResumeVariantEngine``/`ApplicationPreparationEngine`
    already established.
    """
    return ReviewSession(
        id=review_id,
        application_session_id=application_session.id,
        company=application_session.company,
        job_title=application_session.job_title,
        provider=application_session.provider,
        approval_status=result.status,
        review_notes=result.notes,
        created_at=result.review_time,
        approved_at=result.review_time if result.approved else None,
    )
