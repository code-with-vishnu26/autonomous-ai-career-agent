"""Phase 48 (ADR-0066): deterministic provider detection + AdapterRegistry.
No AI, no scoring, no network -- pure pattern matching, offline.
"""

from __future__ import annotations

import pytest

from career_agent.integrations.adapters.arbeitnow import ArbeitnowAdapter
from career_agent.integrations.adapters.ashby import AshbyAdapter
from career_agent.integrations.adapters.base import UnsupportedProviderError
from career_agent.integrations.adapters.greenhouse import GreenhouseAdapter
from career_agent.integrations.adapters.lever import LeverAdapter
from career_agent.integrations.adapters.registry import (
    AdapterRegistry,
    detect_provider,
)
from career_agent.integrations.adapters.remoteok import RemoteOkAdapter
from career_agent.integrations.adapters.remotive import RemotiveAdapter
from career_agent.integrations.adapters.themuse import TheMuseAdapter
from career_agent.integrations.adapters.workday import WorkdayAdapter
from tests._fakes import FakeHttpClient


@pytest.mark.parametrize(
    ("url", "expected_provider"),
    [
        ("https://boards.greenhouse.io/acme/jobs/123", "greenhouse"),
        ("https://jobs.lever.co/acme/abc", "lever"),
        ("https://jobs.ashbyhq.com/acme/xyz", "ashby"),
        ("https://acme.myworkdayjobs.com/en-US/careers/job/1", "workday"),
        ("https://remoteok.com/remote-jobs/789", "remoteok"),
        ("https://remoteok.io/remote-jobs/789", "remoteok"),
        ("https://remotive.com/remote-jobs/acme/backend-456", "remotive"),
        ("https://www.arbeitnow.com/view/backend-eng-1", "arbeitnow"),
        ("https://www.themuse.com/jobs/acme/backend", "themuse"),
    ],
)
def test_detect_provider_matches_every_supported_platform(
    url: str, expected_provider: str
) -> None:
    assert detect_provider(url) == expected_provider


def test_detect_provider_returns_none_for_an_unrecognized_url() -> None:
    assert detect_provider("https://example.com/careers/some-job") is None


def _all_adapters() -> list[object]:
    client = FakeHttpClient()
    return [
        GreenhouseAdapter(["acme"], client=client),
        LeverAdapter(["acme"], client=client),
        AshbyAdapter(["acme"], client=client),
        WorkdayAdapter(),
        RemoteOkAdapter(client=client),
        RemotiveAdapter(client=client),
        ArbeitnowAdapter(client=client),
        TheMuseAdapter(client=client),
    ]


def test_registry_find_returns_the_correct_adapter_for_each_provider() -> None:
    registry = AdapterRegistry(_all_adapters())
    assert registry.find("https://boards.greenhouse.io/acme/jobs/1").provider == (
        "greenhouse"
    )
    assert registry.find("https://jobs.lever.co/acme/abc").provider == "lever"
    assert registry.find("https://jobs.ashbyhq.com/acme/xyz").provider == "ashby"
    assert registry.find(
        "https://acme.myworkdayjobs.com/en-US/careers/job/1"
    ).provider == "workday"


def test_registry_find_raises_for_an_unrecognized_url() -> None:
    registry = AdapterRegistry(_all_adapters())
    with pytest.raises(UnsupportedProviderError):
        registry.find("https://example.com/careers/some-job")


def test_registry_providers_lists_every_registered_provider_in_order() -> None:
    registry = AdapterRegistry(_all_adapters())
    assert registry.providers() == [
        "greenhouse",
        "lever",
        "ashby",
        "workday",
        "remoteok",
        "remotive",
        "arbeitnow",
        "themuse",
    ]


def test_registry_first_registered_adapter_wins_on_a_tie() -> None:
    """If two adapters both claim a URL, the first registered wins -- a
    deterministic, documented tie-break, not undefined behavior."""

    class _AlwaysSupports:
        provider = "always-a"

        def supports(self, url: str) -> bool:
            return True

    class _AlsoAlwaysSupports:
        provider = "always-b"

        def supports(self, url: str) -> bool:
            return True

    registry = AdapterRegistry([_AlwaysSupports(), _AlsoAlwaysSupports()])
    assert registry.find("https://example.com/anything").provider == "always-a"


def test_the_cli_never_needs_to_switch_on_provider_name() -> None:
    """The load-bearing guarantee: given only a URL, the caller gets a
    working adapter without ever naming a specific provider itself."""
    registry = AdapterRegistry(_all_adapters())
    for url in (
        "https://boards.greenhouse.io/acme/jobs/1",
        "https://jobs.lever.co/acme/abc",
    ):
        adapter = registry.find(url)
        assert adapter.supports(url) is True
