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

from career_agent.api.dependencies import (
    get_application_session_store,
    get_submission_result_store,
)
from career_agent.api.security import get_current_user
from career_agent.domain.user import User
from career_agent.storage.excel import (
    application_sessions_xlsx_bytes,
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


@router.get("/applications.xlsx")
def export_applications_xlsx(
    current_user: User = Depends(get_current_user),
    application_session_store=Depends(get_application_session_store),
) -> Response:
    """Every prepared application the caller owns, as an Excel workbook.

    Mirrors what the Applications page shows (``/api/applications``),
    newest first -- company, role, provider, status, résumé variant,
    field-fill progress, warnings.
    """
    sessions = application_session_store.by_user(current_user.id)
    return _xlsx_response(
        application_sessions_xlsx_bytes(sessions), "applications.xlsx"
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
