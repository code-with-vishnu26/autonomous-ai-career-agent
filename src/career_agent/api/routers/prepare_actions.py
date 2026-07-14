"""Web-triggered Prepare: tailor a resume + cover letter for a job (ADR-0085).

The dashboard analogue of ``career-agent prepare`` (Phase 51/ADR-0069),
completing the fully web-driven loop: search (ADR-0081) -> **prepare
(here)** -> review (ADR-0081) -> submit (ADR-0081), no terminal at any
step.

Two things distinguish this from the CLI path, both deliberate:

1. It tailors from the caller's **stored Master Profile** (Phase 64,
   ADR-0082) -- the profile the onboarding wizard writes -- not a
   ``profile.json`` file. This is what makes "the AI builds your résumé
   from the details you entered" actually true for a dashboard user.
2. It runs the *exact same* ``ResumeVariantEngine.build_materials`` (the
   truthfulness gate, ATS threshold, cover-letter assembly all unchanged)
   but does **not** open a browser to pre-fill the live form. That
   pre-fill was only ever a preview; the authoritative form fill and
   résumé upload happen at submit time, behind the human-confirmation gate
   (ADR-0071/0081). Skipping it keeps preparation runnable anywhere and
   deterministic to test.

Fire-and-poll (no confirm step of its own): tailoring sends nothing
outward, so there is no gate to hold here -- the human gate is at submit.
Pending entries live only in this process's memory, the same reasoning
``submission_actions`` relies on: each is tied to a live background task
that cannot survive a restart anyway.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from career_agent.agents.resume.generator import MissingSummaryError
from career_agent.api.dependencies import (
    get_application_session_store,
    get_master_profile_store,
    get_opportunity_repository,
    get_settings,
)
from career_agent.api.security import get_current_user
from career_agent.cli import (
    TruthfulnessRejectedError,
    _notify,
    prepare_application_for_review,
)
from career_agent.domain.ats_scoring import AtsScoreBelowThresholdError
from career_agent.domain.models import Opportunity, Provenance
from career_agent.domain.user import User
from career_agent.llm.promptfoo_gate import PromptfooNotValidatedError
from career_agent.llm.providers import NoLLMProviderConfiguredError

router = APIRouter(prefix="/prepare", tags=["prepare"])

_STALE_ENTRY_SECONDS = 3600.0

PrepareStatus = Literal["PREPARING", "DONE", "FAILED"]


class _PendingPreparation:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.status: PrepareStatus = "PREPARING"
        self.company: str | None = None
        self.job_title: str | None = None
        self.error: str | None = None
        self.application_session_id: str | None = None
        self.created_at = time.monotonic()


_pending: dict[str, _PendingPreparation] = {}


def _prune_stale_entries() -> None:
    cutoff = time.monotonic() - _STALE_ENTRY_SECONDS
    for token in [
        token
        for token, entry in _pending.items()
        if entry.status in ("DONE", "FAILED") and entry.created_at < cutoff
    ]:
        del _pending[token]


class PrepareRequest(BaseModel):
    """Body for ``POST /prepare``."""

    opportunity_id: str


class PastedJobRequest(BaseModel):
    """Body for ``POST /prepare/pasted`` -- a job the user pasted by hand.

    The assisted-apply path for platforms this project deliberately never
    scrapes (LinkedIn, Indeed, Naukri, Workday -- standing invariant 7,
    ADR-0036): the user pastes a posting they found there, the AI tailors a
    résumé + cover letter for it, and they submit on the platform's own
    site. There is no auto-submit here -- a pasted posting's URL resolves
    to no known ATS, so the submission engine already refuses it
    (UNSUPPORTED_PROVIDER); the human applies themselves.
    """

    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    description: str = Field(min_length=1)
    url: str | None = None


def _slugify(value: str) -> str:
    """A stable, lowercase company_id from a pasted company name."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "pasted"


def _opportunity_from_paste(body: PastedJobRequest) -> Opportunity:
    """Build an ad-hoc Opportunity from a hand-pasted posting.

    ``source="job_board"`` and ``method="text_extraction"`` are the honest
    labels for "a human pasted this from a job board"; confidence is 1.0
    because a human curated it (not a heuristic scrape of prose). The
    ``source_url`` is the platform link the user will apply on, if given.
    """
    return Opportunity(
        id=str(uuid.uuid4()),
        company_id=_slugify(body.company),
        canonical_company=body.company,
        title=body.title,
        source="job_board",
        source_url=body.url or "",
        provenance=Provenance(
            method="text_extraction",
            reference=body.url or "user-pasted",
            extraction_confidence=1.0,
        ),
        description_raw=body.description,
        discovered_at=datetime.now(UTC),
    )


class PendingPreparationStatus(BaseModel):
    """Poll target returned by every route in this router."""

    token: str
    status: PrepareStatus
    company: str | None = None
    job_title: str | None = None
    error: str | None = None
    application_session_id: str | None = None


def _status_response(
    token: str, entry: _PendingPreparation
) -> PendingPreparationStatus:
    return PendingPreparationStatus(
        token=token,
        status=entry.status,
        company=entry.company,
        job_title=entry.job_title,
        error=entry.error,
        application_session_id=entry.application_session_id,
    )


async def _run_prepare(
    token: str,
    user_id: str,
    opportunity_id: str | None = None,
    opportunity: Opportunity | None = None,
) -> None:
    """Tailor for one opportunity, given either its id or the object itself.

    The discovered-job path passes ``opportunity_id`` (the opportunity is
    already in the shared catalog). The pasted-job path passes the
    ``opportunity`` object directly -- an ad-hoc posting can collide with
    the repository's dedup-by-fingerprint and never be re-fetchable by id,
    so it is handed through in memory rather than round-tripped (Phase 70
    fix for a "Opportunity not found" failure on paste).
    """
    entry = _pending[token]
    try:
        settings = get_settings()
        profile = get_master_profile_store().get(user_id)
        if profile is None:
            entry.status = "FAILED"
            entry.error = (
                "No Master Profile yet -- complete onboarding first, then prepare."
            )
            return

        if opportunity is None:
            opportunity = await get_opportunity_repository().get(opportunity_id)
        if opportunity is None:
            entry.status = "FAILED"
            entry.error = f"Opportunity {opportunity_id!r} not found."
            return

        entry.company = opportunity.canonical_company
        entry.job_title = opportunity.title

        session = await prepare_application_for_review(
            opportunity=opportunity,
            profile=profile,
            settings=settings,
            user_id=user_id,
        )
        get_application_session_store().save(session, user_id=user_id)
        entry.application_session_id = session.id
        entry.status = "DONE"

        await _notify(
            settings,
            user_id=user_id,
            type="SUCCESS",
            category="resume_prepared",
            title=f"Application prepared: {session.company} - {session.job_title}",
            message=f"Status: {session.status}. Ready to review.",
        )
    except (
        NoLLMProviderConfiguredError,
        PromptfooNotValidatedError,
        MissingSummaryError,
        AtsScoreBelowThresholdError,
        TruthfulnessRejectedError,
    ) as exc:
        entry.status = "FAILED"
        entry.error = str(exc)
    except Exception as exc:  # noqa: BLE001 -- never leave a poller hanging
        entry.status = "FAILED"
        entry.error = str(exc)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PendingPreparationStatus,
)
async def start_preparation(
    body: PrepareRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> PendingPreparationStatus:
    """Start tailoring a résumé + cover letter for one opportunity.

    Returns a token immediately; poll ``GET /prepare/{token}`` for the
    result. On success the poll returns ``application_session_id``, which
    the Review Queue then shows for human approval.
    """
    _prune_stale_entries()
    token = str(uuid.uuid4())
    _pending[token] = _PendingPreparation(current_user.id)
    background_tasks.add_task(
        _run_prepare, token, current_user.id, body.opportunity_id
    )
    return _status_response(token, _pending[token])


@router.post(
    "/pasted",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PendingPreparationStatus,
)
async def start_pasted_preparation(
    body: PastedJobRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    opportunity_repository=Depends(get_opportunity_repository),
) -> PendingPreparationStatus:
    """Tailor for a job the user pasted from a site we don't auto-search.

    Builds an ad-hoc Opportunity from the pasted fields, persists it
    best-effort (so the Review Queue/Excel can reference it), then hands the
    object itself to ``_run_prepare`` -- not just its id. A pasted posting
    can collide with the repository's dedup-by-fingerprint and never be
    re-fetchable by id, which previously surfaced as "Opportunity not
    found"; passing the object through fixes that regardless of dedup.
    """
    opportunity = _opportunity_from_paste(body)
    await opportunity_repository.add(opportunity)
    _prune_stale_entries()
    token = str(uuid.uuid4())
    _pending[token] = _PendingPreparation(current_user.id)
    background_tasks.add_task(
        _run_prepare,
        token,
        current_user.id,
        opportunity_id=opportunity.id,
        opportunity=opportunity,
    )
    return _status_response(token, _pending[token])


@router.get("/{token}", response_model=PendingPreparationStatus)
async def get_preparation_status(
    token: str, current_user: User = Depends(get_current_user)
) -> PendingPreparationStatus:
    """Poll a preparation's current status."""
    entry = _pending.get(token)
    if entry is None or entry.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preparation token not found (expired or never existed).",
        )
    return _status_response(token, entry)
