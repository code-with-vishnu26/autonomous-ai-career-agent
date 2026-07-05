"""Worldwide job-board API sources (Phase 12, ADR-0036).

Eight Tier A sources behind the existing, unchanged
:class:`~career_agent.core.interfaces.OpportunitySource` Protocol -- each a
clean, documented, free JSON API used within its terms:

- **Adzuna** (multi-country incl. India; app_id/app_key)
- **Reed** (UK; API key via Basic auth)
- **USAJobs** (US government; Authorization-Key header + registered UA)
- **Arbeitnow** (Europe; keyless)
- **The Muse** (keyless public API)
- **Remotive** (remote-global; keyless)
- **RemoteOK** (remote-global; keyless, attribution required -- carried in
  every emitted opportunity's provenance reference, per their API terms)
- **Jooble** (multi-country aggregator; free key, POST API)

Tier C (Naukri, Foundit, LinkedIn, Indeed, Seek) is deliberately absent:
none offers a permitted programmatic path (no public API; ToS prohibit
scraping). They are recorded in ADR-0036 as **manual-only** sources -- the
user pastes a posting into the opportunity-file handoff `apply` already
consumes -- and no scraper will be built for them, ever (standing
invariant 7).

Every source populates required ``provenance`` and ``canonical_company``
(ADR-0012/0014) and feeds the existing dedup unchanged. ``since``
filtering is client-side where an API offers none, the same quirk-stays-
private discipline as :class:`~career_agent.plugins.sources.greenhouse.
GreenhouseSource`. A posting with no parseable date is kept (safe toward
not silently dropping a real, fresh posting) -- same rule as Greenhouse.

All are config-bearing (keys/countries/keywords) and registered by the
composition root, never via the zero-config ``discover()`` path.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from career_agent.core.interfaces import HttpClient
from career_agent.domain.identity import domain_of, normalize, opportunity_id
from career_agent.domain.models import Opportunity, Provenance
from career_agent.plugins.sources._dates import as_utc


def _build(
    *,
    provider: str,
    board_token: str,
    native_id: str | None,
    title: str,
    company: str,
    url: str,
    reference: str,
    description: str,
    posted_at: datetime | None,
    location: str | None,
    remote: bool | None,
) -> Opportunity:
    """One shared normalization path so all eight boards emit identically.

    ``canonical_company``: a domain when the posting URL is the employer's
    own, else the normalized company name -- these are aggregator boards,
    so the URL is usually the *board's* domain, which must never become a
    company identity (every posting would collapse); the normalized name
    is the honest fallback (ADR-0014's documented trade-off).
    """
    return Opportunity(
        id=opportunity_id(
            ats_kind=provider,
            board_token=board_token,
            ats_ref=native_id,
            company=company,
            title=title,
            location=location,
        ),
        company_id=normalize(company) or provider,
        canonical_company=normalize(company) or (domain_of(url) or provider),
        title=title,
        source="job_board",
        source_url=url,
        provenance=Provenance(
            method="structured_api",
            reference=reference,
            extraction_confidence=1.0,
        ),
        ats_ref=native_id,
        posted_at=posted_at,
        location=location,
        remote=remote,
        description_raw=description,
        discovered_at=datetime.now(UTC),
    )


def _fresh(opportunity: Opportunity, cutoff: datetime) -> bool:
    return opportunity.posted_at is None or opportunity.posted_at >= cutoff


def _iso_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _unix_dt(value: object) -> datetime | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def _s(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def _items(payload: object, key: str) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        items = payload.get(key, [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


class AdzunaSource:
    """Adzuna search API -- the single best worldwide+India addition."""

    def __init__(
        self,
        *,
        app_id: str,
        app_key: str,
        countries: list[str],
        keywords: str,
        client: HttpClient,
        base_url: str = "https://api.adzuna.com/v1/api/jobs",
    ) -> None:
        """Configure with Adzuna credentials, country codes, and keywords."""
        self._app_id = app_id
        self._app_key = app_key
        self._countries = countries
        self._keywords = keywords
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Fetch page 1 of results per configured country, since-filtered."""
        cutoff = as_utc(since)
        found: list[Opportunity] = []
        for country in self._countries:
            url = f"{self._base_url}/{country}/search/1"
            payload = await self._client.get_json(
                url,
                params={
                    "app_id": self._app_id,
                    "app_key": self._app_key,
                    "what": self._keywords,
                    "results_per_page": "50",
                    "content-type": "application/json",
                },
            )
            for raw in _items(payload, "results"):
                company = raw.get("company")
                company_name = (
                    _s(company, "display_name")
                    if isinstance(company, dict)
                    else ""
                ) or "unknown"
                location = raw.get("location")
                location_name = (
                    _s(location, "display_name")
                    if isinstance(location, dict)
                    else None
                )
                opportunity = _build(
                    provider="adzuna",
                    board_token=country,
                    native_id=_s(raw, "id") or None,
                    title=_s(raw, "title"),
                    company=company_name,
                    url=_s(raw, "redirect_url"),
                    reference=url,
                    description=_s(raw, "description"),
                    posted_at=_iso_dt(raw.get("created")),
                    location=location_name,
                    remote=None,
                )
                if _fresh(opportunity, cutoff):
                    found.append(opportunity)
        return found


class ReedSource:
    """Reed.co.uk search API (UK) -- API key sent as Basic-auth username."""

    def __init__(
        self,
        *,
        api_key: str,
        keywords: str,
        client: HttpClient,
        base_url: str = "https://www.reed.co.uk/api/1.0/search",
    ) -> None:
        """Configure with a Reed API key and search keywords."""
        self._api_key = api_key
        self._keywords = keywords
        self._client = client
        self._base_url = base_url

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Fetch Reed results; Reed exposes no ISO date, so no since-filter.

        Reed's ``date`` field is DD/MM/YYYY; parsed when possible, kept
        when not -- never silently dropped for being unparseable.
        """
        cutoff = as_utc(since)
        token = base64.b64encode(f"{self._api_key}:".encode()).decode()
        payload = await self._client.get_json(
            self._base_url,
            params={"keywords": self._keywords},
            headers={"Authorization": f"Basic {token}"},
        )
        found: list[Opportunity] = []
        for raw in _items(payload, "results"):
            posted = _reed_date(_s(raw, "date"))
            opportunity = _build(
                provider="reed",
                board_token="uk",
                native_id=str(raw.get("jobId", "")) or None,
                title=_s(raw, "jobTitle"),
                company=_s(raw, "employerName") or "unknown",
                url=_s(raw, "jobUrl"),
                reference=self._base_url,
                description=_s(raw, "jobDescription"),
                posted_at=posted,
                location=_s(raw, "locationName") or None,
                remote=None,
            )
            if _fresh(opportunity, cutoff):
                found.append(opportunity)
        return found


class UsaJobsSource:
    """USAJobs (US government) search API -- header-authenticated."""

    def __init__(
        self,
        *,
        api_key: str,
        user_agent: str,
        keywords: str,
        client: HttpClient,
        base_url: str = "https://data.usajobs.gov/api/search",
    ) -> None:
        """Configure with a USAJobs key and its registered user-agent email."""
        self._api_key = api_key
        self._user_agent = user_agent
        self._keywords = keywords
        self._client = client
        self._base_url = base_url

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Fetch USAJobs search results, since-filtered by publication date."""
        cutoff = as_utc(since)
        payload = await self._client.get_json(
            self._base_url,
            params={"Keyword": self._keywords},
            headers={
                "Authorization-Key": self._api_key,
                "User-Agent": self._user_agent,
            },
        )
        found: list[Opportunity] = []
        items = []
        if isinstance(payload, dict):
            result = payload.get("SearchResult")
            if isinstance(result, dict):
                raw_items = result.get("SearchResultItems", [])
                if isinstance(raw_items, list):
                    items = [item for item in raw_items if isinstance(item, dict)]
        for item in items:
            descriptor = item.get("MatchedObjectDescriptor")
            if not isinstance(descriptor, dict):
                continue
            summary = ""
            user_area = descriptor.get("UserArea")
            if isinstance(user_area, dict):
                details = user_area.get("Details")
                if isinstance(details, dict):
                    summary = _s(details, "JobSummary")
            opportunity = _build(
                provider="usajobs",
                board_token="us",
                native_id=_s(descriptor, "PositionID") or None,
                title=_s(descriptor, "PositionTitle"),
                company=_s(descriptor, "OrganizationName") or "US Government",
                url=_s(descriptor, "PositionURI"),
                reference=self._base_url,
                description=summary,
                posted_at=_iso_dt(descriptor.get("PublicationStartDate")),
                location=_s(descriptor, "PositionLocationDisplay") or None,
                remote=None,
            )
            if _fresh(opportunity, cutoff):
                found.append(opportunity)
        return found


class ArbeitnowSource:
    """Arbeitnow job-board API (Europe) -- keyless."""

    def __init__(
        self,
        *,
        client: HttpClient,
        base_url: str = "https://www.arbeitnow.com/api/job-board-api",
    ) -> None:
        """Configure with just an HTTP client -- the API is keyless."""
        self._client = client
        self._base_url = base_url

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Fetch the Arbeitnow board, since-filtered by created_at (unix)."""
        cutoff = as_utc(since)
        payload = await self._client.get_json(self._base_url)
        found: list[Opportunity] = []
        for raw in _items(payload, "data"):
            opportunity = _build(
                provider="arbeitnow",
                board_token="eu",
                native_id=_s(raw, "slug") or None,
                title=_s(raw, "title"),
                company=_s(raw, "company_name") or "unknown",
                url=_s(raw, "url"),
                reference=self._base_url,
                description=_s(raw, "description"),
                posted_at=_unix_dt(raw.get("created_at")),
                location=_s(raw, "location") or None,
                remote=bool(raw.get("remote")) if "remote" in raw else None,
            )
            if _fresh(opportunity, cutoff):
                found.append(opportunity)
        return found


class TheMuseSource:
    """The Muse public jobs API -- keyless (key optional, not required)."""

    def __init__(
        self,
        *,
        client: HttpClient,
        base_url: str = "https://www.themuse.com/api/public/jobs",
    ) -> None:
        """Configure with just an HTTP client."""
        self._client = client
        self._base_url = base_url

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Fetch page 1 of The Muse jobs, since-filtered by publication_date."""
        cutoff = as_utc(since)
        payload = await self._client.get_json(
            self._base_url, params={"page": "1"}
        )
        found: list[Opportunity] = []
        for raw in _items(payload, "results"):
            company = raw.get("company")
            company_name = (
                _s(company, "name") if isinstance(company, dict) else ""
            ) or "unknown"
            locations = raw.get("locations")
            location_name = None
            if isinstance(locations, list) and locations:
                first = locations[0]
                if isinstance(first, dict):
                    location_name = _s(first, "name") or None
            refs = raw.get("refs")
            url = _s(refs, "landing_page") if isinstance(refs, dict) else ""
            opportunity = _build(
                provider="themuse",
                board_token="global",
                native_id=str(raw.get("id", "")) or None,
                title=_s(raw, "name"),
                company=company_name,
                url=url,
                reference=self._base_url,
                description=_s(raw, "contents"),
                posted_at=_iso_dt(raw.get("publication_date")),
                location=location_name,
                remote=None,
            )
            if _fresh(opportunity, cutoff):
                found.append(opportunity)
        return found


class RemotiveSource:
    """Remotive remote-jobs API -- keyless, remote-global."""

    def __init__(
        self,
        *,
        client: HttpClient,
        base_url: str = "https://remotive.com/api/remote-jobs",
    ) -> None:
        """Configure with just an HTTP client."""
        self._client = client
        self._base_url = base_url

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Fetch Remotive's remote jobs, since-filtered by publication_date."""
        cutoff = as_utc(since)
        payload = await self._client.get_json(self._base_url)
        found: list[Opportunity] = []
        for raw in _items(payload, "jobs"):
            opportunity = _build(
                provider="remotive",
                board_token="remote",
                native_id=str(raw.get("id", "")) or None,
                title=_s(raw, "title"),
                company=_s(raw, "company_name") or "unknown",
                url=_s(raw, "url"),
                reference=self._base_url,
                description=_s(raw, "description"),
                posted_at=_iso_dt(raw.get("publication_date")),
                location=_s(raw, "candidate_required_location") or None,
                remote=True,
            )
            if _fresh(opportunity, cutoff):
                found.append(opportunity)
        return found


class RemoteOkSource:
    """RemoteOK API -- keyless; attribution required by their API terms.

    The attribution requirement is honored structurally: every emitted
    opportunity's ``provenance.reference`` carries the RemoteOK API URL,
    and ADR-0036 records the obligation ("data from remoteok.com") for any
    surface that displays these postings. The API's first element is a
    legal-notice object, not a job -- skipped by shape (no ``position``
    key), not by index, so a future payload reordering cannot silently
    drop a real job.
    """

    def __init__(
        self,
        *,
        client: HttpClient,
        base_url: str = "https://remoteok.com/api",
    ) -> None:
        """Configure with just an HTTP client."""
        self._client = client
        self._base_url = base_url

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Fetch RemoteOK's list, skipping the leading legal-notice element."""
        cutoff = as_utc(since)
        payload = await self._client.get_json(self._base_url)
        found: list[Opportunity] = []
        entries = payload if isinstance(payload, list) else []
        for raw in entries:
            if not isinstance(raw, dict) or not _s(raw, "position"):
                continue  # the legal-notice element, or malformed
            opportunity = _build(
                provider="remoteok",
                board_token="remote",
                native_id=str(raw.get("id", "")) or None,
                title=_s(raw, "position"),
                company=_s(raw, "company") or "unknown",
                url=_s(raw, "url"),
                reference=f"{self._base_url} (data from remoteok.com)",
                description=_s(raw, "description"),
                posted_at=_iso_dt(raw.get("date")),
                location=_s(raw, "location") or None,
                remote=True,
            )
            if _fresh(opportunity, cutoff):
                found.append(opportunity)
        return found


class JoobleSource:
    """Jooble multi-country aggregator -- free key, POST API."""

    def __init__(
        self,
        *,
        api_key: str,
        keywords: str,
        location: str,
        client: HttpClient,
        base_url: str = "https://jooble.org/api",
    ) -> None:
        """Configure with a Jooble key, keywords, and a location string."""
        self._api_key = api_key
        self._keywords = keywords
        self._location = location
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """POST a Jooble search, since-filtered by the ``updated`` field."""
        cutoff = as_utc(since)
        url = f"{self._base_url}/{self._api_key}"
        payload = await self._client.post_json(
            url, json={"keywords": self._keywords, "location": self._location}
        )
        found: list[Opportunity] = []
        for raw in _items(payload, "jobs"):
            opportunity = _build(
                provider="jooble",
                board_token=normalize(self._location) or "global",
                native_id=str(raw.get("id", "")) or None,
                title=_s(raw, "title"),
                company=_s(raw, "company") or "unknown",
                url=_s(raw, "link"),
                # The key is in the URL path -- never recorded in provenance.
                reference=f"{self._base_url}/<key>",
                description=_s(raw, "snippet"),
                posted_at=_iso_dt(raw.get("updated")),
                location=_s(raw, "location") or None,
                remote=None,
            )
            if _fresh(opportunity, cutoff):
                found.append(opportunity)
        return found


def _reed_date(value: str) -> datetime | None:
    """Parse Reed's DD/MM/YYYY date format; None when unparseable."""
    if not value:
        return None
    try:
        return as_utc(datetime.strptime(value, "%d/%m/%Y"))  # noqa: DTZ007
    except ValueError:
        return None
