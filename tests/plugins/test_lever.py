"""Tests for the Lever opportunity source (fixture-driven, offline)."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import OpportunitySource
from career_agent.plugins.sources.lever import LeverSource
from tests._fakes import FakeHttpClient, load_fixture

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _source() -> tuple[LeverSource, FakeHttpClient]:
    client = FakeHttpClient(
        {"/postings/acme": load_fixture("lever", "postings.json")}
    )
    return LeverSource(["acme"], client=client), client


def test_lever_satisfies_the_opportunity_source_protocol() -> None:
    source, _ = _source()
    assert isinstance(source, OpportunitySource)


async def test_fetch_normalizes_bare_array_payload() -> None:
    """Lever returns a top-level JSON array (not {"jobs": [...]}); the source
    absorbs that shape difference internally."""
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)

    assert len(opportunities) == 2
    engineer = next(o for o in opportunities if o.title == "Staff Software Engineer")
    assert engineer.source == "ats_api"
    assert engineer.company_id == "acme"
    assert engineer.ats_ref == "a1b2c3d4-0000-4000-8000-000000000001"
    assert engineer.source_url == (
        "https://jobs.lever.co/acme/a1b2c3d4-0000-4000-8000-000000000001"
    )
    assert engineer.location == "Remote - Worldwide"
    assert engineer.remote is True  # workplaceType == "remote"
    assert "Python" in engineer.description_raw
    # createdAt (epoch ms) parsed to an aware UTC datetime
    assert engineer.posted_at == datetime(2026, 6, 20, 14, 30, tzinfo=UTC)

    ae = next(o for o in opportunities if o.title == "Account Executive")
    assert ae.remote is False  # workplaceType == "on-site"


async def test_fetch_passes_mode_json_and_hits_the_company_url() -> None:
    source, client = _source()
    await source.fetch(_EPOCH)
    url, params = client.calls[0]
    assert url.endswith("/postings/acme")
    assert params == {"mode": "json"}


async def test_since_filters_client_side_on_created_at() -> None:
    source, _ = _source()
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)
    opportunities = await source.fetch(cutoff)
    assert [o.title for o in opportunities] == ["Staff Software Engineer"]


async def test_ids_are_deterministic_across_polls() -> None:
    source, _ = _source()
    first = {o.id for o in await source.fetch(_EPOCH)}
    second = {o.id for o in await source.fetch(_EPOCH)}
    assert first == second
