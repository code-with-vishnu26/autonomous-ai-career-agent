"""Lever opportunity source (Phase 4b).

Reads the public Lever postings API
(``api.lever.co/v0/postings/{company}?mode=json``) and normalizes each posting
into a source-agnostic :class:`Opportunity`.

Lever's payload is shaped differently from Greenhouse's, and every difference is
absorbed here rather than in the :class:`OpportunitySource` contract:

- the response is a **bare JSON array**, not ``{"jobs": [...]}``;
- ids are uuid strings, not ints;
- the only timestamp is ``createdAt`` in **epoch milliseconds** -- there is no
  update timestamp, so ``since`` filters on creation time. (The contract's
  notion of ``since`` is "opportunities the source considers new since X"; if a
  posting is edited without being recreated, Lever gives us no signal, which is
  a source limitation, not a contract the caller can rely on for "updated
  since".)

Config-bearing, so registered explicitly by the composition root.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import HttpClient
from career_agent.domain.identity import opportunity_id
from career_agent.domain.models import Opportunity, Provenance
from career_agent.plugins.sources._dates import as_utc

_ATS_KIND = "lever"
_DEFAULT_BASE_URL = "https://api.lever.co/v0/postings"


class LeverSource:
    """Fetch and normalize postings from one or more Lever companies."""

    def __init__(
        self,
        companies: list[str],
        *,
        client: HttpClient,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        """Configure the source with Lever company slugs and an HTTP client."""
        self._companies = companies
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Return postings across all configured companies created since ``since``."""
        cutoff = as_utc(since)
        opportunities: list[Opportunity] = []
        for company in self._companies:
            payload = await self._client.get_json(
                f"{self._base_url}/{company}", params={"mode": "json"}
            )
            for raw in _postings_of(payload):
                opportunity = self._normalize(company, raw)
                if opportunity.posted_at is None or opportunity.posted_at >= cutoff:
                    opportunities.append(opportunity)
        return opportunities

    def _normalize(self, company: str, raw: dict[str, object]) -> Opportunity:
        """Map one raw Lever posting into a normalized :class:`Opportunity`."""
        ats_ref = str(raw["id"])
        title = str(raw["text"])
        location = _location_of(raw)
        posted_at = _parse_created_at(raw.get("createdAt"))
        return Opportunity(
            id=opportunity_id(
                ats_kind=_ATS_KIND,
                board_token=company,
                ats_ref=ats_ref,
                company=company,
                title=title,
                location=location,
            ),
            company_id=company,
            title=title,
            source="ats_api",
            source_url=str(raw.get("hostedUrl", "")),
            provenance=Provenance(
                method="structured_api",
                reference=f"{self._base_url}/{company}/{ats_ref}",
                extraction_confidence=1.0,
            ),
            ats_ref=ats_ref,
            posted_at=posted_at,
            location=location,
            remote=_infer_remote(raw, location),
            description_raw=_description_of(raw),
            discovered_at=datetime.now(UTC),
        )


def _postings_of(payload: object) -> list[dict[str, object]]:
    """Extract postings from Lever's top-level JSON array, defensively."""
    if isinstance(payload, list):
        return [post for post in payload if isinstance(post, dict)]
    return []


def _location_of(raw: dict[str, object]) -> str | None:
    categories = raw.get("categories")
    if isinstance(categories, dict):
        location = categories.get("location")
        if isinstance(location, str) and location.strip():
            return location
    return None


def _infer_remote(raw: dict[str, object], location: str | None) -> bool | None:
    workplace = raw.get("workplaceType")
    if isinstance(workplace, str) and workplace:
        return workplace.casefold() == "remote"
    if location is None:
        return None
    return "remote" in location.casefold()


def _description_of(raw: dict[str, object]) -> str:
    plain = raw.get("descriptionPlain")
    if isinstance(plain, str):
        return plain
    html = raw.get("description")
    return html if isinstance(html, str) else ""


def _parse_created_at(value: object) -> datetime | None:
    """Parse Lever's ``createdAt`` (epoch milliseconds) into an aware UTC dt."""
    if isinstance(value, bool):  # bool is an int subclass; never a timestamp
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    return None
