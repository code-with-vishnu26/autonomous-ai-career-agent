"""Phase 7 / ADR-0018: SubmittableApplication is structurally unconstructible
from an unapproved resume -- the "impossible to construct otherwise"
guarantee, tested against the type itself, not against any Applicator."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from career_agent.domain.models import (
    Application,
    RejectionReason,
    Statement,
    SubmittableApplication,
    TailoredContent,
    TailoredResume,
    TruthfulnessResult,
    to_submittable,
)


def _resume(*, approved: bool) -> TailoredResume:
    statement = Statement(text="x", evidence=None, confidence=0.9, verified=approved)
    rejections = (
        []
        if approved
        else [
            RejectionReason(
                statement_text="x", category="evidence_missing", detail="not grounded"
            )
        ]
    )
    return TailoredResume(
        id="resume-1",
        opportunity_id="opp-1",
        profile_version="profile-v1",
        content=TailoredContent(summary="x"),
        truthfulness=TruthfulnessResult(
            profile_version="profile-v1",
            approved=approved,
            statements=[statement],
            rejections=rejections,
            prompt_version="test-v1",
        ),
    )


def _application(*, approved: bool) -> Application:
    status = "pending" if approved else "failed"
    return Application(
        id="app-1",
        opportunity_id="opp-1",
        resume=_resume(approved=approved),
        status=status,
    )


def test_submittable_application_accepts_an_approved_resume() -> None:
    app = _application(approved=True)
    submittable = SubmittableApplication(application=app)
    assert submittable.application.id == "app-1"


def test_submittable_application_rejects_an_unapproved_resume() -> None:
    app = _application(approved=False)
    with pytest.raises(ValidationError, match="approved"):
        SubmittableApplication(application=app)


def test_to_submittable_is_not_a_separate_bypassable_path() -> None:
    """to_submittable() is a named wrapper, not a second, looser way in --
    it must fail exactly like direct construction, not silently succeed."""
    approved_app = _application(approved=True)
    assert to_submittable(approved_app).application.id == "app-1"

    rejected_app = _application(approved=False)
    with pytest.raises(ValidationError):
        to_submittable(rejected_app)


def test_a_rejected_application_is_still_fully_constructible_for_audit() -> None:
    """Phase 5's audit commitment: a blocked attempt stays visible. Only the
    submission-shaped type is unconstructible from it, not the record itself."""
    app = _application(approved=False)
    assert app.resume.truthfulness.approved is False
    assert app.status == "failed"
