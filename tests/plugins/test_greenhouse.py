"""Tests for the Greenhouse opportunity source (fixture-driven, offline)."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import OpportunitySource
from career_agent.plugins.sources.greenhouse import GreenhouseSource
from tests._fakes import FakeHttpClient, load_fixture

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _source() -> tuple[GreenhouseSource, FakeHttpClient]:
    client = FakeHttpClient(
        {"/boards/acme/jobs": load_fixture("greenhouse", "jobs.json")}
    )
    return GreenhouseSource(["acme"], client=client), client


def test_greenhouse_satisfies_the_opportunity_source_protocol() -> None:
    source, _ = _source()
    assert isinstance(source, OpportunitySource)


async def test_fetch_normalizes_all_jobs() -> None:
    source, client = _source()
    opportunities = await source.fetch(_EPOCH)

    assert len(opportunities) == 2
    engineer = next(o for o in opportunities if o.title == "Senior Backend Engineer")
    assert engineer.source == "ats_api"
    assert engineer.company_id == "acme"
    assert engineer.ats_ref == "4012345"
    assert engineer.source_url == "https://boards.greenhouse.io/acme/jobs/4012345"
    assert engineer.location == "Remote - US"
    assert engineer.remote is True
    assert "Python" in engineer.description_raw
    assert engineer.posted_at == datetime(2026, 6, 20, 18, 30, tzinfo=UTC)

    designer = next(o for o in opportunities if o.title == "Product Designer")
    assert designer.remote is False  # "New York, NY"


async def test_fetch_passes_content_true_and_hits_the_board_url() -> None:
    source, client = _source()
    await source.fetch(_EPOCH)
    url, params = client.calls[0]
    assert url.endswith("/boards/acme/jobs")
    assert params == {"content": "true"}


async def test_since_filters_client_side() -> None:
    """Greenhouse has no server-side `since`; the source filters by updated_at.
    A cutoff after the designer's date but before the engineer's returns only
    the engineer."""
    source, _ = _source()
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)
    opportunities = await source.fetch(cutoff)
    assert [o.title for o in opportunities] == ["Senior Backend Engineer"]


async def test_ids_are_deterministic_across_polls() -> None:
    source, _ = _source()
    first = {o.id for o in await source.fetch(_EPOCH)}
    second = {o.id for o in await source.fetch(_EPOCH)}
    assert first == second  # same postings -> same ids -> dedup works upstream
