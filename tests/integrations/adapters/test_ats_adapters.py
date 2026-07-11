"""Phase 48 (ADR-0066): Greenhouse/Lever/Ashby adapters -- fixture-driven,
offline, no network. Reuses the exact same fixtures the underlying
``OpportunitySource`` tests already use (``tests/plugins/test_{greenhouse,
lever,ashby}.py``), proving the adapter's ``search()`` genuinely delegates
to (rather than reimplements) the existing, real source.
"""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.integrations.adapters.ashby import AshbyAdapter
from career_agent.integrations.adapters.base import WebsiteAdapter
from career_agent.integrations.adapters.greenhouse import GreenhouseAdapter
from career_agent.integrations.adapters.lever import LeverAdapter
from tests._fakes import FakeHttpClient, load_fixture

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _greenhouse_adapter() -> GreenhouseAdapter:
    client = FakeHttpClient(
        {"/boards/acme/jobs": load_fixture("greenhouse", "jobs.json")}
    )
    return GreenhouseAdapter(["acme"], client=client)


def test_greenhouse_adapter_satisfies_the_website_adapter_protocol() -> None:
    assert isinstance(_greenhouse_adapter(), WebsiteAdapter)


def test_greenhouse_adapter_supports_recognizes_its_own_url_shape() -> None:
    adapter = _greenhouse_adapter()
    assert adapter.supports("https://boards.greenhouse.io/acme/jobs/4012345") is True
    assert adapter.supports("https://jobs.lever.co/acme/xyz") is False


async def test_greenhouse_adapter_search_delegates_to_the_real_source() -> None:
    opportunities = await _greenhouse_adapter().search(since=_EPOCH)
    assert len(opportunities) == 2
    assert any(o.title == "Senior Backend Engineer" for o in opportunities)


def test_greenhouse_adapter_capabilities_reflect_verified_text_resume_field() -> None:
    """Greenhouse's real, verified form field (GreenhouseFormFiller) is a
    manual text field, not an upload -- supports_resume_upload must be False."""
    client = FakeHttpClient({})
    adapter = GreenhouseAdapter([], client=client)
    assert adapter.capabilities.supports_resume_upload is False


def test_lever_adapter_supports_recognizes_its_own_url_shape() -> None:
    client = FakeHttpClient({"/postings/acme": load_fixture("lever", "postings.json")})
    adapter = LeverAdapter(["acme"], client=client)
    assert adapter.supports("https://jobs.lever.co/acme/some-id") is True
    assert adapter.supports("https://boards.greenhouse.io/acme/jobs/1") is False


async def test_lever_adapter_search_delegates_to_the_real_source() -> None:
    client = FakeHttpClient({"/postings/acme": load_fixture("lever", "postings.json")})
    adapter = LeverAdapter(["acme"], client=client)
    opportunities = await adapter.search(since=_EPOCH)
    assert len(opportunities) >= 1
    assert all(o.source == "ats_api" for o in opportunities)


def test_lever_adapter_capabilities_reflect_verified_file_upload_field() -> None:
    """Lever's real, verified form field (LeverFormFiller) is a required
    file upload -- supports_resume_upload must be True."""
    client = FakeHttpClient({})
    adapter = LeverAdapter([], client=client)
    assert adapter.capabilities.supports_resume_upload is True


def test_ashby_adapter_supports_recognizes_its_own_url_shape() -> None:
    client = FakeHttpClient({"/job-board/beta": load_fixture("ashby", "jobs.json")})
    adapter = AshbyAdapter(["beta"], client=client)
    assert adapter.supports("https://jobs.ashbyhq.com/beta/some-id") is True
    assert adapter.supports("https://jobs.lever.co/acme/xyz") is False


async def test_ashby_adapter_search_delegates_to_the_real_source() -> None:
    client = FakeHttpClient({"/job-board/beta": load_fixture("ashby", "jobs.json")})
    adapter = AshbyAdapter(["beta"], client=client)
    opportunities = await adapter.search(since=_EPOCH)
    assert len(opportunities) >= 1


def test_ashby_adapter_capabilities_are_entirely_unverified() -> None:
    """No live Ashby application form has been verified (AshbyFormFiller
    is a stub) -- every capability must stay False, unlike Lever/Greenhouse."""
    client = FakeHttpClient({})
    adapter = AshbyAdapter([], client=client)
    assert adapter.capabilities.supports_resume_upload is False
    assert adapter.capabilities.supports_cover_letter_upload is False
    assert adapter.capabilities.supports_easy_apply is False
