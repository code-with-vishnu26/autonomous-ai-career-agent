"""Career Coach endpoints (Phase 57, ADR-0075).

Deliberately under ``/coach/*``, not ``/api/coach/*``: every ``/api/*``
route is structurally proven GET-only
(``test_dashboard_data_routes_are_get_only``, ADR-0072) because none of
them can trigger a real action or cost. Every
route here calls an LLM (a real, costed action, even though none of them
write to a database) -- the same reasoning that put ``/auth/*``/``/user/*``
outside ``/api/*`` in Phase 56, now a third named exception
(``test_auth_and_user_are_the_only_write_capable_routers``).

Every request here is self-contained (resume text + job description text
in the body): there is no server-side stored profile or résumé this API
can read on a multi-user deployment, the same reasoning
``domain/coach_analysis.py`` documents for why it is a distinct, simpler
pipeline from the tailoring engine's own ``score_resume``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from career_agent.agents.coach.cover_letter_assistant import (
    CoachAdvisorError as CoverLetterAdvisorError,
)
from career_agent.agents.coach.cover_letter_assistant import (
    CoverLetterMode,
    CoverLetterTransformRejectedError,
    CoverLetterTransformResult,
    transform_cover_letter,
)
from career_agent.agents.coach.interview_prep import (
    CoachAdvisorError as InterviewPrepAdvisorError,
)
from career_agent.agents.coach.interview_prep import (
    InterviewPrepResult,
    generate_interview_prep,
)
from career_agent.agents.coach.job_match import JobMatchResult, job_match_score
from career_agent.agents.coach.resume_analyzer import ResumeAnalysis, analyze_resume
from career_agent.agents.coach.resume_suggestions import (
    CoachAdvisorError as ResumeSuggestionAdvisorError,
)
from career_agent.agents.coach.resume_suggestions import (
    ResumeSuggestion,
    generate_resume_suggestions,
)
from career_agent.agents.coach.skill_gap import SkillGapReport, skill_gap_report
from career_agent.api.dependencies import get_master_profile_store, get_settings
from career_agent.api.security import get_current_user
from career_agent.core.config import Settings
from career_agent.domain.profile_text import master_profile_to_resume_text
from career_agent.domain.user import User
from career_agent.llm.promptfoo_gate import (
    PromptfooNotValidatedError,
    verify_promptfoo_results,
)
from career_agent.llm.providers import (
    NoLLMProviderConfiguredError,
    select_claim_verifier,
    select_coach_advisor,
)

router = APIRouter(prefix="/coach", tags=["coach"])


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
    )


def _bad_gateway(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


class ResumeJdRequest(BaseModel):
    """Body shared by every endpoint that scores a resume against a JD."""

    resume_text: str
    jd_text: str


class JdRequest(BaseModel):
    """Body for endpoints that only need a job description."""

    jd_text: str


class ProfileMatchResult(BaseModel):
    """Deterministic match of the caller's stored Master Profile to a JD.

    Combines the job-match score and the skill-gap ranking (both
    keyword-based, both naturally read together as "how well do I match,
    and what am I missing") computed from the onboarded profile rather
    than pasted résumé text -- the connective tissue between Phase 64's
    Master Profile and the existing ADR-0075 scorers.
    """

    profile_version: str
    match: JobMatchResult
    skill_gap: SkillGapReport


class CoverLetterTransformRequest(BaseModel):
    """Body for ``POST /coach/cover-letter/transform``."""

    body: str
    mode: CoverLetterMode


def _require_settings_ready(
    settings: Settings, *, results_dir_override: str | None = None
):
    """Build a promptfoo-verified ``ClaimVerifier``, or raise a clear HTTP error.

    Mirrors ``cli.py``'s own ``select_claim_verifier`` +
    ``verify_promptfoo_results`` pair exactly (ADR-0016/0043 discipline) --
    a verifier is never constructed for real use without a live-validated
    promptfoo pass on disk.
    """
    try:
        verifier = select_claim_verifier(settings)
    except NoLLMProviderConfiguredError as exc:
        raise _unavailable(exc) from exc
    results_dir = Path(results_dir_override or settings.promptfoo_results_dir)
    try:
        verify_promptfoo_results(
            verifier.prompt_version, results_dir, provider_id=verifier.provider_id
        )
    except PromptfooNotValidatedError as exc:
        raise _unavailable(exc) from exc
    return verifier


@router.post("/resume-analysis", response_model=ResumeAnalysis)
def resume_analysis(
    body: ResumeJdRequest, current_user: User = Depends(get_current_user)
) -> ResumeAnalysis:
    """Deterministic ATS-style resume scan -- no LLM call, no fabrication risk."""
    return analyze_resume(body.resume_text, body.jd_text)


@router.post("/job-match", response_model=JobMatchResult)
def job_match(
    body: ResumeJdRequest, current_user: User = Depends(get_current_user)
) -> JobMatchResult:
    """Deterministic job match score -- no LLM call, no fabrication risk."""
    return job_match_score(body.resume_text, body.jd_text)


@router.post("/skill-gap", response_model=SkillGapReport)
def skill_gap(
    body: ResumeJdRequest, current_user: User = Depends(get_current_user)
) -> SkillGapReport:
    """Deterministic skill gap ranking -- no LLM call, no fabrication risk."""
    return skill_gap_report(body.resume_text, body.jd_text)


@router.post("/profile-match", response_model=ProfileMatchResult)
def profile_match(
    body: JdRequest,
    current_user: User = Depends(get_current_user),
    master_profile_store=Depends(get_master_profile_store),
) -> ProfileMatchResult:
    """Score the caller's stored Master Profile against a job description.

    Deterministic -- no LLM call, no fabrication risk. Renders the
    onboarded profile (Phase 64) to résumé text and reuses the same
    ADR-0075 keyword scorers the paste-based Coach pages use, so a user
    who onboarded never has to re-type their résumé to see their ATS
    coverage and missing keywords. 404 (not an empty score) when the
    caller has no profile yet, so the UI can send them to onboarding
    rather than showing a misleading 0%.
    """
    profile = master_profile_store.get(current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Master Profile yet -- complete onboarding first.",
        )
    resume_text = master_profile_to_resume_text(profile)
    return ProfileMatchResult(
        profile_version=profile.version,
        match=job_match_score(resume_text, body.jd_text),
        skill_gap=skill_gap_report(resume_text, body.jd_text),
    )


@router.post("/resume-suggestions", response_model=list[ResumeSuggestion])
async def resume_suggestions(
    body: ResumeJdRequest,
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> list[ResumeSuggestion]:
    """LLM-drafted bullet rewordings, verified before being returned.

    Suggestions are advisory only: nothing here is ever written back to
    anything. The frontend's accept/reject step is a purely local UI
    action over this response.
    """
    verifier = _require_settings_ready(settings)
    try:
        advisor = select_coach_advisor(settings)
    except NoLLMProviderConfiguredError as exc:
        raise _unavailable(exc) from exc
    try:
        return await generate_resume_suggestions(
            body.resume_text, body.jd_text, advisor=advisor, verifier=verifier
        )
    except ResumeSuggestionAdvisorError as exc:
        raise _bad_gateway(exc) from exc


@router.post("/cover-letter/transform", response_model=CoverLetterTransformResult)
async def cover_letter_transform(
    body: CoverLetterTransformRequest,
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> CoverLetterTransformResult:
    """Rewrite/shorten/reword a cover letter body, verified before being returned."""
    verifier = _require_settings_ready(settings)
    try:
        advisor = select_coach_advisor(settings)
    except NoLLMProviderConfiguredError as exc:
        raise _unavailable(exc) from exc
    try:
        return await transform_cover_letter(
            body.body, body.mode, advisor=advisor, verifier=verifier
        )
    except CoverLetterAdvisorError as exc:
        raise _bad_gateway(exc) from exc
    except CoverLetterTransformRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/interview-prep", response_model=InterviewPrepResult)
async def interview_prep(
    body: JdRequest,
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> InterviewPrepResult:
    """JD-grounded interview questions and general STAR guidance.

    No ``ClaimVerifier`` gate here -- see ``agents/coach/interview_prep.py``
    for why this feature carries no achievement-fabrication risk.
    """
    try:
        advisor = select_coach_advisor(settings)
    except NoLLMProviderConfiguredError as exc:
        raise _unavailable(exc) from exc
    try:
        return await generate_interview_prep(body.jd_text, advisor=advisor)
    except InterviewPrepAdvisorError as exc:
        raise _bad_gateway(exc) from exc
