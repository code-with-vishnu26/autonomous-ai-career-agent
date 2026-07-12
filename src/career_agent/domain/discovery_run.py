"""``DiscoveryRun``: one web-triggered execution of the discovery pipeline (Phase 63).

Pure data, no I/O -- the same "engine/caller returns data, composition root
persists" shape every other domain model in this package already follows.
This is *not* a new discovery mechanism: it is a status record wrapping the
exact same :func:`~career_agent.cli.build_discovery_sources`/
:func:`~career_agent.cli.run_discover_command` pipeline the CLI's
``career-agent discover`` has always used, so that a dashboard caller (which
cannot block an HTTP request on a multi-source network fetch) has something
to poll while a background task runs it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

#: - ``PENDING``: recorded, background task not yet started.
#: - ``RUNNING``: the background task is actively fetching sources.
#: - ``COMPLETED``: every source was attempted (a per-source failure does
#:   not prevent this -- see ``errors``); ``new_count`` is final.
#: - ``FAILED``: the run itself could not proceed at all (e.g. preferences
#:   failed to load) -- distinct from a per-source fetch failure, which is
#:   recorded in ``errors`` on an otherwise ``COMPLETED`` run.
DiscoveryRunStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]


class DiscoveryRun(BaseModel):
    """One ``POST /discover`` invocation's status, polled by the dashboard."""

    id: str
    user_id: str
    status: DiscoveryRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    new_count: int = 0
    #: Human-readable source labels this run configured (e.g. ``"adzuna"``,
    #: ``"remotive"``) -- the same labels ``run_discover_command`` prints,
    #: shown so a caller can see *what* ran, not just *how many* results.
    source_labels: list[str] = Field(default_factory=list)
    #: One entry per source that raised during ``fetch`` -- mirrors exactly
    #: what ``run_discover_command`` already prints as ``[name] FAILED: ...``,
    #: never a new failure category invented for the API.
    errors: list[str] = Field(default_factory=list)
