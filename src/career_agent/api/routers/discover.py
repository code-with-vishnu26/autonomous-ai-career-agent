"""Web-triggered Discover: the same pipeline ``career-agent discover`` runs (Phase 63).

``POST /discover`` calls the *exact same*
:func:`~career_agent.cli.build_discovery_sources`/
:func:`~career_agent.cli.run_discover_command` functions the CLI command
wires up -- no reimplemented source iteration, dedup, or handoff-file logic
here. The only new code is the HTTP-shaped wrapper: a status record
(:class:`~career_agent.domain.discovery_run.DiscoveryRun`) a caller polls,
since a multi-source network fetch cannot honestly complete within one
request/response cycle.

Search preferences are read from the caller's already-existing
``JobPreferences`` (``GET``/``PUT /user/preferences``, Phase 56) -- this
router adds no second place to configure what a search looks for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from career_agent.api.dependencies import (
    get_discovery_run_store,
    get_opportunity_repository,
    get_settings,
    get_user_preferences_store,
)
from career_agent.api.security import get_current_user
from career_agent.cli import build_discovery_sources, run_discover_command
from career_agent.domain.discovery_run import DiscoveryRun
from career_agent.domain.models import Opportunity
from career_agent.domain.user import User

router = APIRouter(prefix="/discover", tags=["discover"])

#: Same literal default ``career-agent discover --out-dir`` uses (CLI
#: argparse default, not a ``Settings`` field) -- reused rather than
#: invented, so a web-triggered run's handoff files land exactly where a
#: CLI-triggered one already does.
_DEFAULT_OUT_DIR = Path("data/opportunities")


class TriggerDiscoveryRequest(BaseModel):
    """Body for ``POST /discover``."""

    since_days: int = 7


async def _execute_discovery_run(run_id: str, user_id: str, since_days: int) -> None:
    """Background task body -- runs after the triggering request has responded.

    Builds its own store instances rather than receiving FastAPI
    dependencies: ``BackgroundTasks`` runs outside the request's dependency
    scope, the same reason the notification scheduler (Phase 58) builds its
    own stores rather than reusing a request-scoped one.
    """
    settings = get_settings()
    run_store = get_discovery_run_store()
    repo = get_opportunity_repository()
    run = run_store.get(run_id, user_id=user_id)
    if run is None:  # pragma: no cover -- defensive, route always saves PENDING first
        return

    try:
        preferences = get_user_preferences_store().get(user_id)
        sources = build_discovery_sources(settings, preferences)
        run_store.save(
            run.model_copy(
                update={
                    "status": "RUNNING",
                    "source_labels": [name for name, _ in sources],
                }
            )
        )
        new_ids: list[str] = []
        errors: list[str] = []
        await run_discover_command(
            sources,
            repo,
            since=datetime.now(UTC) - timedelta(days=since_days),
            out_dir=_DEFAULT_OUT_DIR,
            on_new_opportunity=lambda opp: new_ids.append(opp.id),
            on_source_error=lambda name, exc: errors.append(f"{name}: {exc}"),
        )
        run_store.save(
            run.model_copy(
                update={
                    "status": "COMPLETED",
                    "completed_at": datetime.now(UTC),
                    "new_count": len(new_ids),
                    "source_labels": [name for name, _ in sources],
                    "errors": errors,
                }
            )
        )
    except Exception as exc:  # noqa: BLE001 -- a run's own failure must still be visible
        run_store.save(
            run.model_copy(
                update={
                    "status": "FAILED",
                    "completed_at": datetime.now(UTC),
                    "errors": [str(exc)],
                }
            )
        )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=DiscoveryRun)
def trigger_discovery(
    body: TriggerDiscoveryRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    discovery_run_store=Depends(get_discovery_run_store),
) -> DiscoveryRun:
    """Kick off the discovery pipeline; returns a ``PENDING`` run immediately.

    Poll ``GET /discover/{run_id}`` for status -- this route never blocks
    on the network fetch itself.
    """
    run = DiscoveryRun(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        status="PENDING",
        started_at=datetime.now(UTC),
    )
    discovery_run_store.save(run)
    background_tasks.add_task(
        _execute_discovery_run, run.id, current_user.id, body.since_days
    )
    return run


@router.get("/runs", response_model=list[DiscoveryRun])
def list_runs(
    current_user: User = Depends(get_current_user),
    discovery_run_store=Depends(get_discovery_run_store),
) -> list[DiscoveryRun]:
    """Every discovery run the caller has triggered, newest first."""
    return discovery_run_store.by_user(current_user.id)


@router.get("/opportunities", response_model=list[Opportunity])
async def list_opportunities(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    opportunity_repository=Depends(get_opportunity_repository),
) -> list[Opportunity]:
    """The most recently discovered opportunities (shared, deduplicated catalog)."""
    return await opportunity_repository.list_recent(limit)


@router.get("/{run_id}", response_model=DiscoveryRun)
def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    discovery_run_store=Depends(get_discovery_run_store),
) -> DiscoveryRun:
    """One discovery run's current status."""
    run = discovery_run_store.get(run_id, user_id=current_user.id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Discovery run not found."
        )
    return run
