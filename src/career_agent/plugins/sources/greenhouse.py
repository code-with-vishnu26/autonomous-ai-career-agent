"""Greenhouse opportunity source (Phase 4a reference source).

Reads the public Greenhouse job-board API
(``boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true``) -- no auth,
full job content, one of the most widely used ATS boards -- and normalizes each
posting into a source-agnostic :class:`Opportunity`.

This is the template every later :class:`OpportunitySource` follows: all the
Greenhouse-specific mechanics (per-board polling, the API's lack of a
server-side ``since`` filter, its HTML ``content`` field) are handled *inside*
this class and never surface in the :class:`OpportunitySource` contract. Adding
Lever/Ashby in Phase 4b must not require touching that interface.

It is *config-bearing* (board tokens + an HTTP client), so it is registered
explicitly by the composition root, not through the zero-argument ``discover()``
path (which remains for zero-config plugins).
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import HttpClient
from career_agent.domain.identity import normalize, opportunity_id
from career_agent.domain.models import Opportunity, Provenance
from career_agent.plugins.sources._dates import as_utc

_ATS_KIND = "greenhouse"
_DEFAULT_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource:
    """Fetch and normalize postings from one or more Greenhouse boards."""

    def __init__(
        self,
        boards: list[str],
        *,
        client: HttpClient,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        """Configure the source with board tokens and an HTTP client.

        Args:
            boards: Greenhouse board tokens to poll (the company identifier in
                a Greenhouse URL, e.g. ``"gitlab"``).
            client: the HTTP port used to fetch JSON (injected so tests can
                replay fixtures with no network).
            base_url: overridable API base, for testing/self-hosting.
        """
        self._boards = boards
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Return postings across all configured boards updated since ``since``.

        Greenhouse has no server-side ``since`` filter, so every board's jobs
        are fetched and filtered client-side by ``updated_at`` -- a quirk kept
        private to this source.
        """
        cutoff = as_utc(since)
        opportunities: list[Opportunity] = []
        for board in self._boards:
            payload = await self._client.get_json(
                f"{self._base_url}/{board}/jobs", params={"content": "true"}
            )
            for raw in _jobs_of(payload):
                opportunity = self._normalize(board, raw)
                if opportunity.posted_at is None or opportunity.posted_at >= cutoff:
                    opportunities.append(opportunity)
        return opportunities

    def _normalize(self, board: str, raw: dict[str, object]) -> Opportunity:
        """Map one raw Greenhouse job into a normalized :class:`Opportunity`."""
        ats_ref = str(raw["id"])
        title = str(raw["title"])
        location = _location_of(raw)
        posted_at = _parse_dt(raw.get("updated_at"))
        return Opportunity(
            id=opportunity_id(
                ats_kind=_ATS_KIND,
                board_token=board,
                ats_ref=ats_ref,
                company=board,
                title=title,
                location=location,
            ),
            company_id=board,
            # ATS exposes no company domain -- canonical identity is the
            # normalized board token (ADR-0014 documented under-merge gap).
            canonical_company=normalize(board),
            title=title,
            source="ats_api",
            source_url=str(raw.get("absolute_url", "")),
            provenance=Provenance(
                method="structured_api",
                reference=f"{self._base_url}/{board}/jobs/{ats_ref}",
                extraction_confidence=1.0,
            ),
            ats_ref=ats_ref,
            posted_at=posted_at,
            location=location,
            remote=_infer_remote(location),
            description_raw=str(raw.get("content", "")),
            discovered_at=datetime.now(UTC),
        )


def _jobs_of(payload: object) -> list[dict[str, object]]:
    """Extract the ``jobs`` list from a Greenhouse API payload defensively."""
    if isinstance(payload, dict):
        jobs = payload.get("jobs", [])
        if isinstance(jobs, list):
            return [job for job in jobs if isinstance(job, dict)]
    return []


def _location_of(raw: dict[str, object]) -> str | None:
    location = raw.get("location")
    if isinstance(location, dict):
        name = location.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return None


def _infer_remote(location: str | None) -> bool | None:
    if location is None:
        return None
    return "remote" in location.casefold()


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None
