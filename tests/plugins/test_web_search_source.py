"""The load-bearing test for 4c slice-2: search hits are not confident
opportunities until confirmed (ADR-0015, applying ADR-0013's held-candidate
pattern to web search).

Same shape as every gate this project has built: catch the phantom, don't
over-catch the real one -- and specifically here, don't trust a URL pattern as
proof. Four cases against one fixture (tests/fixtures/exa/search_results.json,
three results) plus the existing Greenhouse fixture (reused, not duplicated,
as the "real ATS data" the confirmation step parses against):

1. ATS-pattern URL for a job that genuinely exists on the board -> CONFIRMED,
   emitted at confidence 1.0, and it dedups against the ATS source's own record.
2. ATS-pattern URL for a job id that does NOT exist on the board (expired/
   stale index) -> HELD, never emitted, despite matching the URL pattern.
3. A generic career-page/blog URL with no ATS pattern -> HELD.
4. The real, confirmable hit is NOT over-held: exactly one opportunity emits.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import OpportunitySource, SearchQuery
from career_agent.plugins.search.exa import ExaSearchProvider
from career_agent.plugins.sources.web_search import SearchOpportunitySource
from career_agent.storage.memory import (
    InMemoryHeldCandidateSink,
    InMemoryOpportunityRepository,
)
from tests._fakes import FakeHttpClient, load_fixture

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _source() -> tuple[SearchOpportunitySource, InMemoryHeldCandidateSink]:
    # One fake client plays two roles: Exa's POST /search, AND the plain GET
    # confirmation fetch against Greenhouse's board (reusing the real
    # GreenhouseSource fixture) -- exactly what SearchOpportunitySource does in
    # production: search finds candidates, the real ATS source confirms them.
    client = FakeHttpClient(
        {
            "/search": load_fixture("exa", "search_results.json"),
            "/boards/acme/jobs": load_fixture("greenhouse", "jobs.json"),
        }
    )
    provider = ExaSearchProvider(api_key="fake-key", client=client)
    sink = InMemoryHeldCandidateSink()
    source = SearchOpportunitySource(
        provider,
        [SearchQuery(text="acme backend engineer")],
        client=client,
        held_sink=sink,
    )
    return source, sink


def test_search_opportunity_source_satisfies_the_protocol() -> None:
    source, _ = _source()
    assert isinstance(source, OpportunitySource)


async def test_confirmed_ats_hit_emits_at_full_confidence_and_matches_ats_id() -> None:
    """#1: a URL matching a real, parseable Greenhouse job is confirmed by
    actually re-parsing the board -- never trusted on URL shape alone -- and the
    resulting Opportunity IS the ATS source's own record (same ats_ref, same
    method="structured_api", confidence 1.0)."""
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)
    confirmed = [o for o in opportunities if o.ats_ref == "4012345"]
    assert len(confirmed) == 1
    opp = confirmed[0]
    assert opp.title == "Senior Backend Engineer"
    assert opp.provenance.method == "structured_api"  # the ATS source's own method
    assert opp.provenance.extraction_confidence == 1.0


async def test_ats_pattern_url_that_fails_to_confirm_is_held_not_emitted() -> None:
    """#2: the URL matches the Greenhouse pattern, but job id 9999999 does not
    exist on the acme board (expired/stale search index) -- it must be HELD,
    never emitted, despite looking authoritative by URL shape alone. This is
    the parse-or-hold guarantee: confidence 1.0 is earned by parsing, not by
    matching a URL pattern."""
    source, sink = _source()
    opportunities = await source.fetch(_EPOCH)
    assert all(o.ats_ref != "9999999" for o in opportunities)
    held = [h for h in sink.held if "9999999" in h.reference]
    assert len(held) == 1
    assert held[0].reason == "below_threshold"
    assert held[0].extraction_confidence < 0.5


async def test_generic_career_page_hit_is_held() -> None:
    """#3: a URL with no recognized ATS pattern (a blog post) is held -- this
    slice does not attempt to classify arbitrary web content as a confident
    posting."""
    source, sink = _source()
    opportunities = await source.fetch(_EPOCH)
    assert all("acme.com/blog" not in o.source_url for o in opportunities)
    held = [h for h in sink.held if "acme.com/blog" in h.reference]
    assert len(held) == 1
    assert held[0].reason == "ambiguous_parse"


async def test_the_real_hit_is_not_over_held() -> None:
    """#4: the false-positive guard, same as every matrix in this project --
    exactly one of the three search hits is genuinely confirmable, and it must
    emit. A mechanism that holds everything is as broken as one that holds
    nothing."""
    source, _ = _source()
    opportunities = await source.fetch(_EPOCH)
    assert len(opportunities) == 1


async def test_confirmed_hit_dedups_against_the_ats_sources_own_record() -> None:
    """The ADR-0014 payoff: a confirmed search hit reuses the ATS source's
    exact id, so feeding both into the shared repository collapses to one
    record -- not a bypass of the settled two-key identity."""
    from career_agent.plugins.sources.greenhouse import GreenhouseSource

    search_source, _ = _source()
    gh_client = FakeHttpClient(
        {"/boards/acme/jobs": load_fixture("greenhouse", "jobs.json")}
    )
    gh_source = GreenhouseSource(["acme"], client=gh_client)

    repo = InMemoryOpportunityRepository()
    gh_opportunities = await gh_source.fetch(_EPOCH)
    for opp in gh_opportunities:
        await repo.add(opp)

    search_opportunities = await search_source.fetch(_EPOCH)
    confirmed = next(o for o in search_opportunities if o.ats_ref == "4012345")
    assert await repo.add(confirmed) is False  # already known via the ATS source
