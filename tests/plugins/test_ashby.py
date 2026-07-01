"""Tests for the Ashby opportunity source (fixture-driven, offline)."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import OpportunitySource
from career_agent.plugins.sources.ashby import AshbySource
from tests._fakes import FakeHttpClient, load_fixture

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _source() -> tuple[AshbySource, FakeHttpClient]:
    client = FakeHttpClient(
        {"/job-board/beta": load_fixture("ashby", "jobs.json")}
    )
    return AshbySource(["beta"], client=client), client


def test_ashby_satisfies_the_opportunity_source_protocol() -> None:
    source, _ = _source()
    assert isinstance(source, OpportunitySource)


async def test_fetch_normalizes_jobs_and_uses_explicit_is_remote() -> None:
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)

    assert len(opportunities) == 2
    engineer = next(o for o in opportunities if o.title == "Senior Platform Engineer")
    assert engineer.source == "ats_api"
    assert engineer.company_id == "beta"
    assert engineer.ats_ref == "b2c3d4e5-0000-4000-8000-000000000001"
    assert engineer.source_url == (
        "https://jobs.ashbyhq.com/beta/b2c3d4e5-0000-4000-8000-000000000001"
    )
    assert engineer.location == "Remote (US)"
    assert engineer.remote is True  # explicit isRemote bool, not inferred
    assert "infrastructure" in engineer.description_raw
    assert engineer.posted_at == datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    assert engineer.provenance.method == "structured_api"
    assert engineer.provenance.extraction_confidence == 1.0

    writer = next(o for o in opportunities if o.title == "Technical Writer")
    assert writer.remote is False  # explicit isRemote == false, despite Berlin


async def test_fetch_hits_the_job_board_url() -> None:
    source, client = _source()
    await source.fetch(_EPOCH)
    url, params = client.calls[0]
    assert url.endswith("/job-board/beta")
    assert params is None


async def test_since_filters_client_side_on_published_at() -> None:
    source, _ = _source()
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)
    opportunities = await source.fetch(cutoff)
    assert [o.title for o in opportunities] == ["Senior Platform Engineer"]


async def test_ids_are_deterministic_across_polls() -> None:
    source, _ = _source()
    first = {o.id for o in await source.fetch(_EPOCH)}
    second = {o.id for o in await source.fetch(_EPOCH)}
    assert first == second
