"""Phase 48 (ADR-0066): WorkdayAdapter -- explicit stub, no real
integration exists. Proves the stub fails loudly and names the real gap,
never silently returning an empty result indistinguishable from "searched
and found nothing."
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from career_agent.integrations.adapters.base import (
    FeatureUnavailableError,
    WebsiteAdapter,
)
from career_agent.integrations.adapters.workday import WorkdayAdapter

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def test_workday_adapter_satisfies_the_website_adapter_protocol() -> None:
    assert isinstance(WorkdayAdapter(), WebsiteAdapter)


def test_workday_adapter_supports_its_own_hostname() -> None:
    adapter = WorkdayAdapter()
    assert (
        adapter.supports("https://acme.myworkdayjobs.com/en-US/careers/job/1")
        is True
    )
    assert adapter.supports("https://boards.greenhouse.io/acme/jobs/1") is False


async def test_workday_adapter_search_raises_feature_unavailable_not_empty() -> None:
    adapter = WorkdayAdapter()
    with pytest.raises(FeatureUnavailableError):
        await adapter.search(since=_EPOCH)


def test_workday_adapter_capabilities_are_entirely_unverified() -> None:
    adapter = WorkdayAdapter()
    assert adapter.capabilities.supports_resume_upload is False
    assert adapter.capabilities.supports_cover_letter_upload is False
    assert adapter.capabilities.supports_easy_apply is False
