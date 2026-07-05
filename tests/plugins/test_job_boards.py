"""Phase 12 / ADR-0036: the eight Tier A worldwide job-board sources.

Fixture-driven via FakeHttpClient -- no network, ever. Each source is
proven to: normalize its real payload shape into a valid Opportunity with
required provenance + canonical_company, since-filter client-side, keep
undated postings, and authenticate the way its real API demands.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.plugins.sources.job_boards import (
    AdzunaSource,
    ArbeitnowSource,
    JoobleSource,
    ReedSource,
    RemoteOkSource,
    RemotiveSource,
    TheMuseSource,
    UsaJobsSource,
)
from tests._fakes import FakeHttpClient

_OLD = datetime(2020, 1, 1, tzinfo=UTC)
_CUTOFF = datetime(2026, 6, 1, tzinfo=UTC)


async def test_adzuna_normalizes_and_queries_each_configured_country():
    client = FakeHttpClient(
        default={
            "results": [
                {
                    "id": "42",
                    "title": "Backend Engineer",
                    "company": {"display_name": "Acme India"},
                    "location": {"display_name": "Bengaluru, India"},
                    "redirect_url": "https://www.adzuna.in/details/42",
                    "created": "2026-06-15T00:00:00Z",
                    "description": "Python and Django role.",
                }
            ]
        }
    )
    source = AdzunaSource(
        app_id="id",
        app_key="key",
        countries=["gb", "in"],
        keywords="python",
        client=client,
    )
    found = await source.fetch(_OLD)
    assert len(found) == 2  # one per country page
    assert {url for url, _params in client.calls} == {
        "https://api.adzuna.com/v1/api/jobs/gb/search/1",
        "https://api.adzuna.com/v1/api/jobs/in/search/1",
    }
    opportunity = found[0]
    assert opportunity.source == "job_board"
    assert opportunity.canonical_company == "acme india"
    assert opportunity.provenance.extraction_confidence == 1.0
    assert opportunity.title == "Backend Engineer"


async def test_reed_uses_basic_auth_and_parses_uk_dates():
    client = FakeHttpClient(
        default={
            "results": [
                {
                    "jobId": 7,
                    "jobTitle": "Platform Engineer",
                    "employerName": "Acme UK",
                    "locationName": "London",
                    "jobUrl": "https://www.reed.co.uk/jobs/7",
                    "date": "20/06/2026",
                    "jobDescription": "Kubernetes platform work.",
                }
            ]
        }
    )
    source = ReedSource(api_key="reed-key", keywords="python", client=client)
    found = await source.fetch(_CUTOFF)
    assert len(found) == 1
    assert found[0].posted_at == datetime(2026, 6, 20, tzinfo=UTC)
    # Basic auth: key as username, empty password, base64-encoded.
    header = client.get_headers[0]["Authorization"]
    assert header.startswith("Basic ")
    import base64

    assert base64.b64decode(header.removeprefix("Basic ")).decode() == "reed-key:"


async def test_usajobs_sends_required_headers_and_unwraps_nested_shape():
    client = FakeHttpClient(
        default={
            "SearchResult": {
                "SearchResultItems": [
                    {
                        "MatchedObjectDescriptor": {
                            "PositionID": "ABC-123",
                            "PositionTitle": "IT Specialist",
                            "OrganizationName": "Department of Examples",
                            "PositionURI": "https://www.usajobs.gov/job/1",
                            "PublicationStartDate": "2026-06-10",
                            "PositionLocationDisplay": "Washington, DC",
                            "UserArea": {"Details": {"JobSummary": "Serve."}},
                        }
                    }
                ]
            }
        }
    )
    source = UsaJobsSource(
        api_key="usa-key",
        user_agent="user@example.com",
        keywords="engineer",
        client=client,
    )
    found = await source.fetch(_CUTOFF)
    assert len(found) == 1
    assert found[0].company_id == "department of examples"
    headers = client.get_headers[0]
    assert headers["Authorization-Key"] == "usa-key"
    assert headers["User-Agent"] == "user@example.com"


async def test_arbeitnow_parses_unix_timestamps_and_remote_flag():
    client = FakeHttpClient(
        default={
            "data": [
                {
                    "slug": "backend-eng-1",
                    "company_name": "Acme GmbH",
                    "title": "Backend Engineer",
                    "description": "Go and Postgres.",
                    "remote": True,
                    "url": "https://www.arbeitnow.com/view/backend-eng-1",
                    "location": "Berlin",
                    "created_at": int(datetime(2026, 6, 20, tzinfo=UTC).timestamp()),
                }
            ]
        }
    )
    found = await ArbeitnowSource(client=client).fetch(_CUTOFF)
    assert len(found) == 1
    assert found[0].remote is True
    assert found[0].posted_at == datetime(2026, 6, 20, tzinfo=UTC)


async def test_themuse_unwraps_nested_company_locations_and_refs():
    client = FakeHttpClient(
        default={
            "results": [
                {
                    "id": 99,
                    "name": "Data Engineer",
                    "company": {"name": "Acme Muse"},
                    "locations": [{"name": "New York, NY"}],
                    "refs": {"landing_page": "https://themuse.com/jobs/99"},
                    "publication_date": "2026-06-12T08:00:00Z",
                    "contents": "ETL pipelines.",
                }
            ]
        }
    )
    found = await TheMuseSource(client=client).fetch(_CUTOFF)
    assert len(found) == 1
    assert found[0].location == "New York, NY"
    assert found[0].source_url == "https://themuse.com/jobs/99"


async def test_remotive_marks_remote_and_since_filters():
    client = FakeHttpClient(
        default={
            "jobs": [
                {
                    "id": 1,
                    "title": "Old Role",
                    "company_name": "Acme",
                    "url": "https://remotive.com/jobs/1",
                    "publication_date": "2020-01-02T00:00:00",
                    "candidate_required_location": "Worldwide",
                    "description": "Old.",
                },
                {
                    "id": 2,
                    "title": "Fresh Role",
                    "company_name": "Acme",
                    "url": "https://remotive.com/jobs/2",
                    "publication_date": "2026-06-20T00:00:00",
                    "candidate_required_location": "Worldwide",
                    "description": "Fresh.",
                },
            ]
        }
    )
    found = await RemotiveSource(client=client).fetch(_CUTOFF)
    assert [opportunity.title for opportunity in found] == ["Fresh Role"]
    assert found[0].remote is True


async def test_remoteok_skips_legal_notice_by_shape_and_carries_attribution():
    client = FakeHttpClient(
        default=[
            {"legal": "API terms: link back to remoteok.com"},  # notice, no job
            {
                "id": "555",
                "position": "SRE",
                "company": "Acme Remote",
                "url": "https://remoteok.com/jobs/555",
                "date": "2026-06-18T00:00:00+00:00",
                "description": "Observability.",
                "location": "Worldwide",
            },
        ]
    )
    found = await RemoteOkSource(client=client).fetch(_CUTOFF)
    assert len(found) == 1  # the legal notice was skipped by shape, not index
    assert "remoteok.com" in found[0].provenance.reference  # attribution


async def test_jooble_posts_search_and_never_records_key_in_provenance():
    client = FakeHttpClient(
        default={
            "jobs": [
                {
                    "id": 314,
                    "title": "ML Engineer",
                    "company": "Acme AI",
                    "location": "Bengaluru",
                    "link": "https://jooble.org/jdp/314",
                    "updated": "2026-06-19T00:00:00",
                    "snippet": "PyTorch role.",
                }
            ]
        }
    )
    source = JoobleSource(
        api_key="secret-key", keywords="ml", location="India", client=client
    )
    found = await source.fetch(_CUTOFF)
    assert len(found) == 1
    url, body = client.post_calls[0]
    assert url.endswith("/secret-key")
    assert body == {"keywords": "ml", "location": "India"}
    # The key is in the request URL by API design, but must never be
    # recorded into stored provenance.
    assert "secret-key" not in found[0].provenance.reference


async def test_undated_postings_are_kept_not_silently_dropped():
    client = FakeHttpClient(
        default={
            "jobs": [
                {
                    "id": 3,
                    "title": "No Date Role",
                    "company_name": "Acme",
                    "url": "https://remotive.com/jobs/3",
                    "publication_date": "",
                    "candidate_required_location": "Worldwide",
                    "description": "x",
                }
            ]
        }
    )
    found = await RemotiveSource(client=client).fetch(_CUTOFF)
    assert len(found) == 1  # same keep-when-undated rule as Greenhouse
    assert found[0].posted_at is None


async def test_all_eight_sources_satisfy_the_unchanged_protocol():
    from career_agent.core.interfaces import OpportunitySource

    client = FakeHttpClient(default={})
    sources = [
        AdzunaSource(
            app_id="a", app_key="b", countries=["gb"], keywords="x", client=client
        ),
        ReedSource(api_key="k", keywords="x", client=client),
        UsaJobsSource(api_key="k", user_agent="u@e.com", keywords="x", client=client),
        ArbeitnowSource(client=client),
        TheMuseSource(client=client),
        RemotiveSource(client=client),
        RemoteOkSource(client=client),
        JoobleSource(api_key="k", keywords="x", location="", client=client),
    ]
    for source in sources:
        assert isinstance(source, OpportunitySource)
