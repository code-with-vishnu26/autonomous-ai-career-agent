"""Excel download endpoints for the dashboard (Phase 65, ADR-0083).

The CLI has always produced a formatted, filterable ``.xlsx`` of every
application (``career-agent export``, Phase 13). This exposes the same
artifact to a dashboard user, scoped to their own rows -- so "store the
details in a spreadsheet" needs no terminal.

GET-only and read-only: these routes build a workbook from the caller's
own ``ApplicationSession``/``SubmissionResult`` rows and stream it back.
They never trigger discovery, preparation, or a submission, and they
never write to any store -- so no safety gate this project relies on is
involved. They live under ``/export`` rather than ``/api`` only because
they return a binary attachment, not JSON (the ``/api/*`` GET-only
structural proof is about JSON data routes).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from career_agent.agents.research.company_research import research_company
from career_agent.agents.resume.file_renderer import (
    PdfConversionUnavailableError,
    convert_to_pdf,
    render_resume_docx,
)
from career_agent.api.dependencies import (
    get_application_session_store,
    get_master_profile_store,
    get_opportunity_repository,
    get_resume_variant_store,
    get_search_provider,
    get_settings,
    get_submission_result_store,
)
from career_agent.api.security import get_current_user
from career_agent.core.config import Settings
from career_agent.core.security import (
    InvalidTokenError,
    create_resume_download_token,
    decode_resume_download_token,
)
from career_agent.domain.company_research import CompanyResearch
from career_agent.domain.user import User
from career_agent.storage.excel import (
    enriched_applications_xlsx_bytes,
    submissions_xlsx_bytes,
)

router = APIRouter(prefix="/export", tags=["export"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx_response(data: bytes, filename: str) -> Response:
    """A downloadable ``.xlsx`` attachment response."""
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


#: How long a résumé-download link embedded in an exported workbook stays
#: valid -- long enough that a spreadsheet someone keeps for a job search
#: (weeks to a few months) still works, short enough that a leaked/shared
#: file doesn't grant access forever.
_RESUME_LINK_EXPIRY_DAYS = 90


async def _enriched_application_rows(
    sessions, opportunity_repository, search_provider, user_id: str, settings: Settings
) -> list[dict[str, object]]:
    """Join each application to its Opportunity + public company research.

    Company research is looked up once per distinct company (cached), so a
    long history is a bounded number of web-search calls -- and none at all
    when no search key is configured (``research_company`` short-circuits).
    Every URL here is public (the job posting, the company's careers page,
    the research sources) or a signed capability link scoped to exactly one
    résumé the caller owns; the cover letter is the caller's own, inlined.
    """
    research_cache: dict[str, CompanyResearch] = {}
    rows: list[dict[str, object]] = []
    for session in sessions:
        opportunity = await opportunity_repository.get(session.opportunity_id)
        company = session.company
        if company not in research_cache:
            research_cache[company] = await research_company(company, search_provider)
        research = research_cache[company]
        resume_pdf_url = ""
        if session.resume_variant_id and settings.jwt_secret_key:
            token = create_resume_download_token(
                user_id=user_id,
                resume_variant_id=session.resume_variant_id,
                secret_key=settings.jwt_secret_key,
                expires_in_days=_RESUME_LINK_EXPIRY_DAYS,
            )
            resume_pdf_url = (
                f"{settings.api_base_url.rstrip('/')}"
                f"/export/resume/{session.resume_variant_id}.pdf?token={token}"
            )
        rows.append(
            {
                "prepared": session.created_at.isoformat(),
                "company": company,
                "role": session.job_title,
                "location": (opportunity.location if opportunity else "") or "",
                "remote": (
                    ("yes" if opportunity.remote else "no")
                    if opportunity and opportunity.remote is not None
                    else ""
                ),
                "source": opportunity.source if opportunity else "",
                "posted": (
                    opportunity.posted_at.isoformat()
                    if opportunity and opportunity.posted_at
                    else ""
                ),
                "status": str(session.status),
                "job_url": (
                    session.url
                    or (opportunity.source_url if opportunity else "")
                ),
                "careers_url": research.careers_url or "",
                "linkedin_url": research.linkedin_url or "",
                "company_research": research.summary,
                "research_sources": "\n".join(s.url for s in research.sources),
                "resume_pdf_url": resume_pdf_url,
                "cover_letter": session.cover_letter_body or "",
            }
        )
    return rows


@router.get("/applications.xlsx")
async def export_applications_xlsx(
    current_user: User = Depends(get_current_user),
    application_session_store=Depends(get_application_session_store),
    opportunity_repository=Depends(get_opportunity_repository),
    search_provider=Depends(get_search_provider),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Every prepared application the caller owns, as an enriched workbook.

    Beyond what the Applications page shows, each row joins the posting's
    accurate details (location, remote, source, posted date, the job URL),
    public web-search company research (a source-backed summary, the
    careers page, the company's LinkedIn page, source links), a signed
    link to the exact tailored résumé PDF that was submitted, and the
    tailored cover letter inline -- the "accurate details, company links,
    which résumé was submitted, and company research in one sheet" the
    owner asked for. Company research is empty-but-honest when no Exa/
    Google CSE key is configured; it never fabricates.
    """
    sessions = application_session_store.by_user(current_user.id)
    rows = await _enriched_application_rows(
        sessions, opportunity_repository, search_provider, current_user.id, settings
    )
    return _xlsx_response(
        enriched_applications_xlsx_bytes(rows), "applications.xlsx"
    )


@router.get("/submissions.xlsx")
def export_submissions_xlsx(
    current_user: User = Depends(get_current_user),
    submission_result_store=Depends(get_submission_result_store),
) -> Response:
    """Every submission attempt the caller owns, as an Excel workbook.

    Mirrors what the Submission Queue / History pages show
    (``/api/submissions``) -- company, role, provider, status, whether it
    was actually submitted, confirmation id, and any refusal/warnings.
    """
    results = submission_result_store.by_user(current_user.id)
    return _xlsx_response(submissions_xlsx_bytes(results), "submissions.xlsx")


@router.get("/resume/{variant_id}.pdf")
async def export_resume_pdf(
    variant_id: str,
    token: str,
    resume_variant_store=Depends(get_resume_variant_store),
    master_profile_store=Depends(get_master_profile_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    """The tailored résumé PDF for one résumé variant -- token-authenticated.

    Deliberately **not** session-authenticated (no ``get_current_user``
    dependency): this is the link an Excel row's "Résumé (PDF)" hyperlink
    points at, opened later from Excel itself with no
    ``Authorization`` header available. ``token`` (Phase 71, ADR-0089) is
    the capability -- a signed JWT scoped to exactly this ``variant_id``
    and its owning user, so possessing the link *is* the authorization,
    the same model a presigned download URL uses anywhere else.

    Renders on demand from the stored ``ResumeVariant`` content + the
    owner's ``MasterProfile`` -- the exact same renderer
    ``prepare``/``submit`` use, so what downloads is the real tailored
    résumé, not a stale cached copy. Returns 503 (not a 500) when this
    server has no PDF converter installed -- a real, named environment
    constraint (ADR-0080's precedent for "the capability may not exist
    here"), not a bug.
    """
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Resume downloads are unavailable until JWT_SECRET_KEY is set.",
        )
    try:
        claims = decode_resume_download_token(
            token, secret_key=settings.jwt_secret_key
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This résumé link is invalid or has expired.",
        ) from exc
    if claims.resume_variant_id != variant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This résumé link is invalid or has expired.",
        )

    owned = any(
        v.id == variant_id for v in resume_variant_store.by_user(claims.user_id)
    )
    variant = resume_variant_store.get(variant_id) if owned else None
    profile = master_profile_store.get(claims.user_id) if owned else None
    if variant is None or profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Résumé not found."
        )

    artifacts_dir = Path(settings.artifacts_dir) / "web_downloads"
    docx_artifact = render_resume_docx(
        variant.id, variant.content, profile, artifacts_dir
    )
    try:
        pdf_artifact = convert_to_pdf(docx_artifact, artifacts_dir)
    except PdfConversionUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PDF rendering is unavailable on this server: {exc}",
        ) from exc

    return Response(
        content=Path(pdf_artifact.path).read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="resume-{variant_id}.pdf"'
        },
    )
