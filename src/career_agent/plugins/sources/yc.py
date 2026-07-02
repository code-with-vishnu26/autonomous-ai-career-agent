"""YC (Y Combinator) opportunity source (Phase 4b-feeds).

Reads a structured YC hiring feed (``hiring.json``-style: a single global JSON
document listing companies' open roles) and normalizes each role into an
:class:`Opportunity` with ``source="yc"``.

YC is *structured but not an ATS*: unlike Greenhouse/Lever/Ashby it is a single
global feed rather than a per-company board, and it carries a real company
identity (name/slug) rather than an ATS board token. But it is still ground
truth -- discrete role objects with clean fields -- so extraction confidence is
1.0 (``method="structured_feed"``). It is the trivial-confidence end of the
provenance/confidence channel (ADR-0012); the freeform Hacker News source is
what later exercises confidence < 1.0.

The exact public feed schema is confirmed when run on the user's own machine
(the host is blocked by the sandbox egress policy); this source is built and
tested against a recorded fixture of the assumed shape.

Config-bearing (a feed URL + an HTTP client), so registered explicitly by the
composition root.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import HttpClient
from career_agent.domain.identity import normalize, opportunity_id
from career_agent.domain.models import Opportunity, Provenance
from career_agent.plugins.sources._dates import as_utc

_SOURCE_KIND = "yc"
_DEFAULT_FEED_URL = "https://www.ycombinator.com/hiring.json"


class YCSource:
    """Fetch and normalize roles from the YC hiring feed."""

    def __init__(
        self,
        *,
        client: HttpClient,
        feed_url: str = _DEFAULT_FEED_URL,
    ) -> None:
        """Configure the source with the YC feed URL and an HTTP client."""
        self._client = client
        self._feed_url = feed_url

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Return roles from the feed posted since ``since``."""
        cutoff = as_utc(since)
        payload = await self._client.get_json(self._feed_url)
        opportunities: list[Opportunity] = []
        for raw in _jobs_of(payload):
            opportunity = self._normalize(raw)
            if opportunity.posted_at is None or opportunity.posted_at >= cutoff:
                opportunities.append(opportunity)
        return opportunities

    def _normalize(self, raw: dict[str, object]) -> Opportunity:
        """Map one raw YC role into a normalized :class:`Opportunity`."""
        role_id = str(raw["id"])
        title = str(raw["role"])
        company_slug, company_name = _company_of(raw)
        location = _location_of(raw)
        posted_at = _parse_dt(raw.get("posted_at"))
        source_url = str(raw.get("url", ""))
        return Opportunity(
            id=opportunity_id(
                ats_kind=_SOURCE_KIND,
                board_token=company_slug,
                ats_ref=role_id,
                company=company_name,
                title=title,
                location=location,
            ),
            company_id=company_slug,
            canonical_company=normalize(company_slug),  # real slug (ADR-0014)
            title=title,
            source="yc",
            source_url=source_url,
            provenance=Provenance(
                method="structured_feed",
                reference=source_url or f"{self._feed_url}#{role_id}",
                extraction_confidence=1.0,
            ),
            ats_ref=role_id,
            posted_at=posted_at,
            location=location,
            remote=_remote_of(raw, location),
            description_raw=str(raw.get("description", "")),
            discovered_at=datetime.now(UTC),
        )


def _jobs_of(payload: object) -> list[dict[str, object]]:
    """Extract the role list from a YC feed payload defensively."""
    if isinstance(payload, dict):
        jobs = payload.get("jobs", [])
        if isinstance(jobs, list):
            return [job for job in jobs if isinstance(job, dict)]
    return []


def _company_of(raw: dict[str, object]) -> tuple[str, str]:
    """Return ``(slug, name)`` for the role's company, with sane fallbacks."""
    company = raw.get("company")
    if isinstance(company, dict):
        name = company.get("name")
        slug = company.get("slug")
        name_s = name if isinstance(name, str) and name.strip() else "unknown"
        slug_s = slug if isinstance(slug, str) and slug.strip() else name_s
        return slug_s, name_s
    return "unknown", "unknown"


def _location_of(raw: dict[str, object]) -> str | None:
    location = raw.get("location")
    if isinstance(location, str) and location.strip():
        return location
    return None


def _remote_of(raw: dict[str, object], location: str | None) -> bool | None:
    remote = raw.get("remote")
    if isinstance(remote, bool):
        return remote
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
