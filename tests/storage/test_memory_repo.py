"""Tests for the in-memory OpportunityRepository."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import OpportunityRepository
from career_agent.domain.models import Opportunity, Provenance
from career_agent.storage.memory import InMemoryOpportunityRepository


def _opp(opportunity_id: str = "id-1") -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        title="Engineer",
        source="ats_api",
        source_url="https://example.invalid/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.invalid/api/1",
            extraction_confidence=1.0,
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_in_memory_repo_satisfies_the_contract() -> None:
    assert isinstance(InMemoryOpportunityRepository(), OpportunityRepository)


def test_in_memory_repo_exposes_only_the_contract_methods() -> None:
    """Fidelity guard: the in-memory impl must not add public convenience
    methods the SQLite impl won't also have, or the later swap isn't a drop-in.
    Only `add` and `get` are public."""
    public = {
        name
        for name in vars(InMemoryOpportunityRepository).keys()
        if not name.startswith("_")
    }
    assert public == {"add", "get"}


async def test_add_is_idempotent_by_id() -> None:
    repo = InMemoryOpportunityRepository()
    assert await repo.add(_opp("id-1")) is True
    assert await repo.add(_opp("id-1")) is False  # duplicate id


async def test_get_returns_stored_or_none() -> None:
    repo = InMemoryOpportunityRepository()
    stored = _opp("id-1")
    await repo.add(stored)
    assert (await repo.get("id-1")) == stored
    assert (await repo.get("missing")) is None
