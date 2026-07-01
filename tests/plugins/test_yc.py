"""Tests for the YC opportunity source (fixture-driven, offline)."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import OpportunitySource
from career_agent.plugins.sources.yc import YCSource
from tests._fakes import FakeHttpClient, load_fixture

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _source() -> tuple[YCSource, FakeHttpClient]:
    client = FakeHttpClient({"hiring.json": load_fixture("yc", "hiring.json")})
    return YCSource(client=client), client


def test_yc_satisfies_the_opportunity_source_protocol() -> None:
    source, _ = _source()
    assert isinstance(source, OpportunitySource)


async def test_fetch_normalizes_structured_feed() -> None:
    """YC is a single global feed carrying real company identity (name/slug),
    not a per-company board; the source absorbs that difference internally."""
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)

    assert len(opportunities) == 2
    engineer = next(o for o in opportunities if o.title == "Founding Engineer")
    assert engineer.source == "yc"
    assert engineer.company_id == "nimbus-labs"  # real slug, not an ATS token
    assert engineer.location == "Remote (US)"
    assert engineer.remote is True
    assert engineer.posted_at == datetime(2026, 6, 18, tzinfo=UTC)
    assert engineer.source_url.endswith("/jobs/yc-9001")


async def test_yc_sets_structured_feed_provenance_with_full_confidence() -> None:
    """The trivial-confidence end of the ADR-0012 channel: a structured feed is
    ground truth, so confidence is exactly 1.0 and method marks it structured."""
    source, _ = _source()
    engineer = next(
        o for o in await source.fetch(_EPOCH) if o.title == "Founding Engineer"
    )
    assert engineer.provenance.method == "structured_feed"
    assert engineer.provenance.extraction_confidence == 1.0
    assert engineer.provenance.reference.endswith("/jobs/yc-9001")


async def test_since_filters_client_side() -> None:
    source, _ = _source()
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)
    opportunities = await source.fetch(cutoff)
    assert [o.title for o in opportunities] == ["Founding Engineer"]


async def test_ids_are_deterministic_across_polls() -> None:
    source, _ = _source()
    first = {o.id for o in await source.fetch(_EPOCH)}
    second = {o.id for o in await source.fetch(_EPOCH)}
    assert first == second
