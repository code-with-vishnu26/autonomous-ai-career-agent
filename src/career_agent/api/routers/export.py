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

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from career_agent.agents.research.company_research import research_company
from career_agent.api.dependencies import (
    get_application_session_store,
    get_opportunity_repository,
    get_search_provider,
    get_submission_result_store,
)
from career_agent.api.security import get_current_user
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


async def _enriched_application_rows(
    sessions, opportunity_repository, search_provider
) -> list[dict[str, object]]:
    """Join each application to its Opportunity + public company research.

    Company research is looked up once per distinct company (cached), so a
    long history is a bounded number of web-search calls -- and none at all
    when no search key is configured (``research_company`` short-circuits).
    Every URL here is public (the job posting, the company's careers page,
    the research sources); the cover letter is the caller's own, inlined.
    """
    research_cache: dict[str, CompanyResearch] = {}
    rows: list[dict[str, object]] = []
    for session in sessions:
        opportunity = await opportunity_repository.get(session.opportunity_id)
        company = session.company
        if company not in research_cache:
            research_cache[company] = await research_company(company, search_provider)
        research = research_cache[company]
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
                "company_research": research.summary,
                "research_sources": "\n".join(s.url for s in research.sources),
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
) -> Response:
    """Every prepared application the caller owns, as an enriched workbook.

    Beyond what the Applications page shows, each row joins the posting's
    accurate details (location, remote, source, posted date, the job URL)
    and public web-search company research (a source-backed summary, the
    careers page, source links) plus the tailored cover letter inline --
    the "accurate details, company links, and company research in one
    sheet" the owner asked for. Company research is empty-but-honest when
    no Exa/Google CSE key is configured; it never fabricates.
    """
    sessions = application_session_store.by_user(current_user.id)
    rows = await _enriched_application_rows(
        sessions, opportunity_repository, search_provider
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
