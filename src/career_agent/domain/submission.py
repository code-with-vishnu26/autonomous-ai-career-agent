"""Submission Engine's pure result type (Phase 53, ADR-0071).

Mirrors the "engine returns data, caller persists" and "pure results live
in domain/" precedents Phases 50-52 already established for
``ResumeVariant``/``ApplicationSession``/``ReviewSession``.

**No verified success-page detection exists anywhere in this codebase.**
This project has never confirmed a "Thank you" banner, a confirmation
number field, or a success redirect against a real, live posting on any
platform -- the identical "don't guess a selector" discipline that already
kept ``LeverFormFiller``/``AshbyFormFiller`` honest (ADR-0028) and kept
``SessionManager``'s login detection caller-supplied rather than
platform-specific (Phase 47). The only verified success signal this
codebase has ever established is :class:`~career_agent.agents.apply.
browser_applicator.BrowserApplicator`'s own event distinction:
``ApplicationSubmitted`` (submit was clicked and no challenge selector is
visible afterward) vs. ``HumanActionRequired`` (a pause). ``confirmation_id``/
``confirmation_url`` therefore stay ``None`` with an explicit warning
recorded, rather than fabricated from an unverified heuristic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

#: - ``SUBMITTED``: ``BrowserApplicator`` returned ``ApplicationSubmitted``.
#: - ``FAILED``: a submission attempt was made (page opened, form touched)
#:   and did not complete -- a network error, a validation refusal
#:   (``UnsupportedFormFieldsError``), a missing required résumé artifact.
#: - ``UNKNOWN``: a pause (``HumanActionRequired``) could not be resolved
#:   automatically within this run -- genuinely ambiguous, never collapsed
#:   into ``FAILED`` or ``SUBMITTED`` (mirrors ``SubmissionOutcome.
#:   OUTCOME_UNCERTAIN``, domain/execution.py, ADR-0050).
#: - ``ABORTED``: the browser/session became unusable mid-flow.
#: - ``CANCELLED``: the human declined the final countdown/confirmation
#:   prompt -- every earlier precondition held, but the human said no.
#: - ``REFUSED``: the execution-safety boundary (``domain/execution.py``,
#:   ADR-0050) refused *before* any browser action was attempted --
#:   distinct from ``FAILED`` (an attempt happened) the same way
#:   ``Application.status``'s ``"rejected"`` is kept distinct from
#:   ``"failed"`` (ADR-0023): a refusal is a precondition problem, an
#:   attempt failure is a real-world event.
SubmissionStatus = Literal[
    "SUBMITTED", "FAILED", "UNKNOWN", "ABORTED", "CANCELLED", "REFUSED"
]


class SubmissionResult(BaseModel):
    """One submission attempt's full, final outcome."""

    id: str
    application_session_id: str
    review_session_id: str
    opportunity_id: str
    provider: str
    company: str
    job_title: str
    submitted: bool
    status: SubmissionStatus
    confirmation_id: str | None = None
    confirmation_url: str | None = None
    submitted_at: datetime | None = None
    duration_seconds: float | None = None
    warnings: list[str] = Field(default_factory=list)
    #: Set only when ``status == "REFUSED"`` -- the exact
    #: ``domain.execution`` reason code (e.g. ``REFUSED_MANUAL_ONLY_SOURCE``)
    #: or a precondition name this module checks before ever consulting
    #: that boundary (e.g. ``"review_not_approved"``).
    refusal_reason: str | None = None
