"""Ashby opportunity source (Phase 4b).

Reads the public Ashby job-board API
(``api.ashbyhq.com/posting-api/job-board/{name}``) and normalizes each posting
into a source-agnostic :class:`Opportunity`.

Ashby's shape differs again, and every difference stays private to this source:

- the response wraps postings in ``{"jobs": [...]}`` (like Greenhouse) but with
  uuid ids and flat fields;
- the timestamp is ``publishedAt`` as an ISO-8601 string;
- remote status is an **explicit** ``isRemote`` boolean, so it is used directly
  rather than inferred from the location text.

Config-bearing, so registered explicitly by the composition root.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import HttpClient
from career_agent.domain.identity import opportunity_id
from career_agent.domain.models import Opportunity
from career_agent.plugins.sources._dates import as_utc

_ATS_KIND = "ashby"
_DEFAULT_BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource:
    """Fetch and normalize postings from one or more Ashby job boards."""

    def __init__(
        self,
        boards: list[str],
        *,
        client: HttpClient,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        """Configure the source with Ashby job-board names and an HTTP client."""
        self._boards = boards
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Return postings across all configured boards published since ``since``."""
        cutoff = as_utc(since)
        opportunities: list[Opportunity] = []
        for board in self._boards:
            payload = await self._client.get_json(f"{self._base_url}/{board}")
            for raw in _jobs_of(payload):
                opportunity = self._normalize(board, raw)
                if opportunity.posted_at is None or opportunity.posted_at >= cutoff:
                    opportunities.append(opportunity)
        return opportunities

    def _normalize(self, board: str, raw: dict[str, object]) -> Opportunity:
        """Map one raw Ashby posting into a normalized :class:`Opportunity`."""
        ats_ref = str(raw["id"])
        title = str(raw["title"])
        location = _location_of(raw)
        posted_at = _parse_published_at(raw.get("publishedAt"))
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
            title=title,
            source="ats_api",
            source_url=str(raw.get("jobUrl", "")),
            ats_ref=ats_ref,
            posted_at=posted_at,
            location=location,
            remote=_remote_of(raw, location),
            description_raw=_description_of(raw),
            discovered_at=datetime.now(UTC),
        )


def _jobs_of(payload: object) -> list[dict[str, object]]:
    """Extract the ``jobs`` list from an Ashby API payload defensively."""
    if isinstance(payload, dict):
        jobs = payload.get("jobs", [])
        if isinstance(jobs, list):
            return [job for job in jobs if isinstance(job, dict)]
    return []


def _location_of(raw: dict[str, object]) -> str | None:
    location = raw.get("location")
    if isinstance(location, str) and location.strip():
        return location
    return None


def _remote_of(raw: dict[str, object], location: str | None) -> bool | None:
    is_remote = raw.get("isRemote")
    if isinstance(is_remote, bool):
        return is_remote
    if location is None:
        return None
    return "remote" in location.casefold()


def _description_of(raw: dict[str, object]) -> str:
    html = raw.get("descriptionHtml")
    if isinstance(html, str):
        return html
    plain = raw.get("descriptionPlain")
    return plain if isinstance(plain, str) else ""


def _parse_published_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None
