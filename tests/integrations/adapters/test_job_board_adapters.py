"""Phase 48 (ADR-0066): the four keyless job-board adapters (RemoteOK,
Remotive, Arbeitnow, The Muse) -- fixture-driven, offline, no network.
Structurally identical to each other (each wraps one keyless
``OpportunitySource``), so covered in one parametrized-by-hand file rather
than four near-duplicate ones.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.integrations.adapters.arbeitnow import ArbeitnowAdapter
from career_agent.integrations.adapters.base import WebsiteAdapter
from career_agent.integrations.adapters.remoteok import RemoteOkAdapter
from career_agent.integrations.adapters.remotive import RemotiveAdapter
from career_agent.integrations.adapters.themuse import TheMuseAdapter
from tests._fakes import FakeHttpClient

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NOW = int(datetime(2026, 6, 20, tzinfo=UTC).timestamp())

_ARBEITNOW_PAYLOAD = {
    "data": [
        {
            "slug": "backend-eng-1",
            "company_name": "Acme GmbH",
            "title": "Backend Engineer",
            "description": "Go and Postgres.",
            "remote": True,
            "url": "https://www.arbeitnow.com/view/backend-eng-1",
            "location": "Berlin",
            "created_at": _NOW,
        }
    ]
}

_THEMUSE_PAYLOAD = {
    "results": [
        {
            "id": 123,
            "name": "Backend Engineer",
            "contents": "Python and FastAPI.",
            "refs": {"landing_page": "https://www.themuse.com/jobs/acme/backend"},
            "locations": [{"name": "Remote"}],
            "company": {"name": "Acme"},
            "publication_date": "2026-06-20T00:00:00Z",
        }
    ]
}

_REMOTIVE_PAYLOAD = {
    "jobs": [
        {
            "id": 456,
            "title": "Backend Engineer",
            "company_name": "Acme",
            "candidate_required_location": "Worldwide",
            "url": "https://remotive.com/remote-jobs/acme/backend-456",
            "description": "Python and Django.",
            "publication_date": "2026-06-20T00:00:00Z",
        }
    ]
}

_REMOTEOK_PAYLOAD = [
    {"legal": "https://remoteok.com/legal"},
    {
        "id": "789",
        "position": "Backend Engineer",
        "company": "Acme",
        "url": "https://remoteok.com/remote-jobs/789",
        "description": "Python and FastAPI.",
        "location": "Worldwide",
        "date": "2026-06-20T00:00:00+00:00",
    },
]


async def test_remoteok_adapter_search_delegates_to_the_real_source() -> None:
    client = FakeHttpClient(default=_REMOTEOK_PAYLOAD)
    adapter = RemoteOkAdapter(client=client)
    assert isinstance(adapter, WebsiteAdapter)
    opportunities = await adapter.search(since=_EPOCH)
    assert len(opportunities) == 1
    assert opportunities[0].title == "Backend Engineer"


def test_remoteok_adapter_supports_both_known_hostnames() -> None:
    adapter = RemoteOkAdapter(client=FakeHttpClient())
    assert adapter.supports("https://remoteok.com/remote-jobs/789") is True
    assert adapter.supports("https://remoteok.io/remote-jobs/789") is True
    assert adapter.supports("https://boards.greenhouse.io/acme/jobs/1") is False


async def test_remotive_adapter_search_delegates_to_the_real_source() -> None:
    client = FakeHttpClient(default=_REMOTIVE_PAYLOAD)
    adapter = RemotiveAdapter(client=client)
    assert isinstance(adapter, WebsiteAdapter)
    opportunities = await adapter.search(since=_EPOCH)
    assert len(opportunities) == 1
    assert opportunities[0].remote is True


def test_remotive_adapter_supports_its_own_hostname() -> None:
    adapter = RemotiveAdapter(client=FakeHttpClient())
    assert adapter.supports("https://remotive.com/remote-jobs/acme/backend-456") is True
    assert adapter.supports("https://remoteok.com/remote-jobs/789") is False


async def test_arbeitnow_adapter_search_delegates_to_the_real_source() -> None:
    client = FakeHttpClient(default=_ARBEITNOW_PAYLOAD)
    adapter = ArbeitnowAdapter(client=client)
    assert isinstance(adapter, WebsiteAdapter)
    opportunities = await adapter.search(since=_EPOCH)
    assert len(opportunities) == 1
    assert opportunities[0].remote is True


def test_arbeitnow_adapter_supports_its_own_hostname() -> None:
    adapter = ArbeitnowAdapter(client=FakeHttpClient())
    assert adapter.supports("https://www.arbeitnow.com/view/backend-eng-1") is True
    assert (
        adapter.supports("https://remotive.com/remote-jobs/acme/backend-456")
        is False
    )


async def test_themuse_adapter_search_delegates_to_the_real_source() -> None:
    client = FakeHttpClient(default=_THEMUSE_PAYLOAD)
    adapter = TheMuseAdapter(client=client)
    assert isinstance(adapter, WebsiteAdapter)
    opportunities = await adapter.search(since=_EPOCH)
    assert len(opportunities) == 1


def test_themuse_adapter_supports_its_own_hostname() -> None:
    adapter = TheMuseAdapter(client=FakeHttpClient())
    assert adapter.supports("https://www.themuse.com/jobs/acme/backend") is True
    assert adapter.supports("https://www.arbeitnow.com/view/backend-eng-1") is False


def test_every_job_board_adapter_capabilities_are_entirely_unverified() -> None:
    """None of these aggregators has a verified application-form filler --
    every capability must default False."""
    for adapter in (
        RemoteOkAdapter(client=FakeHttpClient()),
        RemotiveAdapter(client=FakeHttpClient()),
        ArbeitnowAdapter(client=FakeHttpClient()),
        TheMuseAdapter(client=FakeHttpClient()),
    ):
        assert adapter.capabilities.supports_resume_upload is False
        assert adapter.capabilities.supports_cover_letter_upload is False
        assert adapter.capabilities.supports_easy_apply is False
