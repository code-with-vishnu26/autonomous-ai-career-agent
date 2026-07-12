"""Web-triggered Submit: prepare + confirm, over the exact same SubmissionEngine.

``career-agent submit``, Phase 53/ADR-0071, extended Phase 63/ADR-0081.

Kept as a separate router from ``submissions.py`` (which stays ``/api/submissions``,
read-only, submission *history*) since these routes can trigger a real
submission attempt -- following the established "write-capable routers live
off the ``/api/`` prefix" convention.

Two-step flow, mirroring the CLI's countdown-then-ENTER gate over HTTP:

1. ``POST /submissions/prepare`` starts a background task that runs the
   *exact same* :func:`~career_agent.cli.submit_prepared_application` the
   CLI uses (fresh re-tailor, promptfoo gate, then
   :meth:`~career_agent.agents.submission.submission_engine.SubmissionEngine.submit`)
   and returns a token immediately.
2. ``POST /submissions/{token}/confirm`` is the human's explicit choice --
   resolved into the *same* asyncio ``Future`` the background task's
   ``confirm_fn`` is blocked awaiting. Declining, or never confirming
   within :data:`_CONFIRMATION_TIMEOUT_SECONDS`, raises
   :class:`~career_agent.agents.submission.submission_engine.CancelledByUserError`
   -- ``SubmissionEngine.submit`` already handles that as ``CANCELLED``.
   Silence can never imply "yes."

Pending entries live only in this process's memory (module-level dict,
never persisted) -- the same reasoning
:class:`~career_agent.agents.apply.browser_applicator.BrowserApplicator`'s
own in-memory pause-token dict already relies on: each is tied to a live
asyncio ``Task`` that cannot survive a process restart anyway.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from career_agent.agents.submission.submission_engine import CancelledByUserError
from career_agent.api.dependencies import (
    get_application_session_store,
    get_opportunity_repository,
    get_review_session_store,
    get_settings,
)
from career_agent.api.security import get_current_user
from career_agent.cli import (
    SubmissionMaterialsError,
    _notify,
    submit_prepared_application,
)
from career_agent.domain.user import User
from career_agent.integrations.adapters.base import FeatureUnavailableError
from career_agent.storage.profile import ProfileValidationError, load_master_profile
from career_agent.storage.sqlite import (
    SqliteResumeVariantStore,
    SqliteSubmissionResultStore,
)

router = APIRouter(prefix="/submissions", tags=["submissions"])

#: Same literal default every CLI command uses (``--profile`` argparse
#: default), reused rather than invented -- MasterProfile has no per-user
#: API store (ADR-0081); this project's single-operator profile framing
#: (ADR-0000/ADR-0078) applies here too.
_DEFAULT_PROFILE_PATH = Path("profile.json")

#: Never auto-confirm on silence -- a bounded wait, then CANCELLED, the
#: same "no default to yes" discipline the CLI's own countdown gate holds.
_CONFIRMATION_TIMEOUT_SECONDS = 300

_STALE_ENTRY_SECONDS = 3600.0

PendingStatus = Literal[
    "PREPARING", "AWAITING_CONFIRMATION", "SUBMITTING", "DONE", "FAILED"
]


class _PendingSubmission:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.status: PendingStatus = "PREPARING"
        self.future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self.company: str | None = None
        self.job_title: str | None = None
        self.error: str | None = None
        self.result_id: str | None = None
        self.created_at = time.monotonic()


_pending: dict[str, _PendingSubmission] = {}


def _prune_stale_entries() -> None:
    cutoff = time.monotonic() - _STALE_ENTRY_SECONDS
    stale = [
        token
        for token, entry in _pending.items()
        if entry.status in ("DONE", "FAILED") and entry.created_at < cutoff
    ]
    for token in stale:
        del _pending[token]


class PrepareSubmissionRequest(BaseModel):
    """Body for ``POST /submissions/prepare``."""

    application_session_id: str


class ConfirmSubmissionRequest(BaseModel):
    """Body for ``POST /submissions/{token}/confirm``."""

    approved: bool


class PendingSubmissionStatus(BaseModel):
    """Poll target returned by every route in this router."""

    token: str
    status: PendingStatus
    company: str | None = None
    job_title: str | None = None
    error: str | None = None
    result_id: str | None = None


def _status_response(token: str, entry: _PendingSubmission) -> PendingSubmissionStatus:
    return PendingSubmissionStatus(
        token=token,
        status=entry.status,
        company=entry.company,
        job_title=entry.job_title,
        error=entry.error,
        result_id=entry.result_id,
    )


async def _run_prepare_and_submit(
    token: str, user_id: str, application_session_id: str
) -> None:
    entry = _pending[token]
    try:
        settings = get_settings()
        session = next(
            (
                candidate
                for candidate in get_application_session_store().by_user(user_id)
                if candidate.id == application_session_id
            ),
            None,
        )
        if session is None:
            raise SubmissionMaterialsError("Application session not found.")
        entry.company = session.company
        entry.job_title = session.job_title

        review = next(
            (
                candidate
                for candidate in get_review_session_store().by_user(user_id)
                if candidate.application_session_id == session.id
                and candidate.approval_status == "APPROVED"
            ),
            None,
        )
        if review is None:
            raise SubmissionMaterialsError(
                "No approved review decision found for this application session -- "
                "approve it in the Review Queue first."
            )

        opportunity = await get_opportunity_repository().get(session.opportunity_id)
        if opportunity is None:
            raise SubmissionMaterialsError(
                f"Opportunity {session.opportunity_id!r} not found."
            )

        if not _DEFAULT_PROFILE_PATH.exists():
            raise SubmissionMaterialsError(
                f"No {_DEFAULT_PROFILE_PATH} found in the server's working "
                "directory -- run `career-agent onboard` first."
            )
        try:
            profile = load_master_profile(_DEFAULT_PROFILE_PATH)
        except ProfileValidationError as exc:
            raise SubmissionMaterialsError(
                f"Could not load {_DEFAULT_PROFILE_PATH}: {exc}"
            ) from exc

        variant_store = SqliteResumeVariantStore(Path(settings.database_path))
        stored_variant = (
            variant_store.get(session.resume_variant_id)
            if session.resume_variant_id
            else None
        )

        async def confirm_fn() -> bool:
            entry.status = "AWAITING_CONFIRMATION"
            try:
                approved = await asyncio.wait_for(
                    entry.future, timeout=_CONFIRMATION_TIMEOUT_SECONDS
                )
            except TimeoutError as exc:
                raise CancelledByUserError from exc
            if not approved:
                raise CancelledByUserError
            entry.status = "SUBMITTING"
            return True

        result = await submit_prepared_application(
            opportunity=opportunity,
            profile=profile,
            review=review,
            application_session=session,
            stored_variant=stored_variant,
            settings=settings,
            confirm_fn=confirm_fn,
            auto_close_on_pause=True,
        )

        SqliteSubmissionResultStore(Path(settings.database_path)).save(
            result, user_id=user_id
        )
        entry.result_id = result.id
        entry.status = "DONE"

        _submission_category = {
            "SUBMITTED": ("SUCCESS", "submission_completed"),
            "CANCELLED": ("INFO", "submission_cancelled"),
        }.get(result.status, ("ERROR", "submission_failed"))
        await _notify(
            settings,
            user_id=user_id,
            type=_submission_category[0],
            category=_submission_category[1],
            title=(
                f"Submission {result.status.lower()}: {result.company} - "
                f"{result.job_title}"
            ),
            message=f"Status: {result.status}."
            + (f" Reason: {result.refusal_reason}" if result.refusal_reason else ""),
        )
    except (SubmissionMaterialsError, FeatureUnavailableError) as exc:
        entry.status = "FAILED"
        entry.error = str(exc)
    except Exception as exc:  # noqa: BLE001 -- never leave a poller hanging on FAILED
        entry.status = "FAILED"
        entry.error = str(exc)


@router.post(
    "/prepare",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PendingSubmissionStatus,
)
async def prepare_submission(
    body: PrepareSubmissionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> PendingSubmissionStatus:
    """Start a submission attempt.

    Fresh re-tailor + promptfoo gate + the final human-confirmation gate --
    returns a token to poll and confirm.

    Declared ``async def`` deliberately (not a plain ``def``): FastAPI runs
    ``async def`` routes directly on the main event loop, the same loop the
    background task and ``confirm_submission`` below run on -- so the
    ``asyncio.Future`` this creates is only ever touched from one thread,
    with no ``call_soon_threadsafe`` needed. A plain ``def`` route would run
    in a worker thread pool instead, making that future thread-unsafe.
    """
    _prune_stale_entries()
    token = str(uuid.uuid4())
    _pending[token] = _PendingSubmission(current_user.id)
    background_tasks.add_task(
        _run_prepare_and_submit, token, current_user.id, body.application_session_id
    )
    return _status_response(token, _pending[token])


@router.get("/prepare/{token}", response_model=PendingSubmissionStatus)
async def get_prepare_status(
    token: str, current_user: User = Depends(get_current_user)
) -> PendingSubmissionStatus:
    """Poll a submission attempt's current status."""
    entry = _pending.get(token)
    if entry is None or entry.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission token not found (expired or never existed).",
        )
    return _status_response(token, entry)


@router.post("/{token}/confirm", response_model=PendingSubmissionStatus)
async def confirm_submission(
    token: str,
    body: ConfirmSubmissionRequest,
    current_user: User = Depends(get_current_user),
) -> PendingSubmissionStatus:
    """The real, final, un-bypassable human gate.

    Exactly the same one ``career-agent submit``'s countdown/ENTER prompt
    enforces, just reached over HTTP. Declining (or a second confirm after
    the first already resolved it) never re-triggers anything.
    """
    entry = _pending.get(token)
    if entry is None or entry.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission token not found (expired or never existed).",
        )
    if entry.status != "AWAITING_CONFIRMATION":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Not currently awaiting confirmation (status={entry.status!r}).",
        )
    if not entry.future.done():
        entry.future.set_result(body.approved)
    return _status_response(token, entry)
